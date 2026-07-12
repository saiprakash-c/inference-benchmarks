"""
derisk/derisk_metrics_cosmos_reason.py

Evaluates Cosmos-Reason2-2B on LingoQA (eval split, 500 QA pairs / 100 video clips)
using Lingo-Judge — matching Alpamayo 1.5's evaluation protocol exactly.

Run with:
    bazel run //derisk:derisk_metrics_cosmos_reason -- \\
        --val_parquet /workspace/data/lingoqa/evaluation/val.parquet \\
        --images_zip  /workspace/data/lingoqa/evaluation/evaluation/images.zip

Dataset files (already downloaded):
    val.parquet  — 1000 rows, 500 unique questions, 2 annotator answers each
    images.zip   — frames at images/val/<segment_id>/<frame>.jpg
"""

from __future__ import annotations

import argparse
import ctypes
import io
import os
import sys
import time
import zipfile
from typing import Any


# ---------------------------------------------------------------------------
# Pre-load CUDA .so files before importing torch (Bazel RPATH fix)
# ---------------------------------------------------------------------------

def _preload_cuda_libs() -> None:
    for path in sys.path:
        nvidia_dir = os.path.join(path, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        try:
            pkg_names = os.listdir(nvidia_dir)
        except OSError:
            continue
        for pkg in pkg_names:
            # Skip cudnn — torch has its own bundled cuDNN and loading a
            # pip-installed nvidia-cudnn before it causes
            # CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH on Conv3d.
            if pkg == "cudnn":
                continue
            lib_dir = os.path.join(nvidia_dir, pkg, "lib")
            if not os.path.isdir(lib_dir):
                continue
            try:
                entries = os.listdir(lib_dir)
            except OSError:
                continue
            for fname in entries:
                if ".so" not in fname:
                    continue
                full = os.path.join(lib_dir, fname)
                try:
                    ctypes.CDLL(full, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


_preload_cuda_libs()

import torch  # noqa: E402
import transformers  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL: str = "nvidia/Cosmos-Reason2-2B"
LINGO_JUDGE_MODEL: str = "wayveai/Lingo-Judge"
LINGO_BATCH_SIZE: int = 64
MAX_NEW_TOKENS: int = 64
MAX_FRAMES: int = 8           # cap frames per clip to limit token budget
# Matches Alpamayo 1.5's processor config (NVlabs/alpamayo1.5 helper.py).
MIN_PIXELS: int = 163_840     # 512×320
MAX_PIXELS: int = 196_608     # 512×384


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Stage 0 — Load LingoQA eval split from parquet + zip
# ---------------------------------------------------------------------------

def stage0_load_dataset(val_parquet: str, images_zip: str) -> list[dict[str, Any]]:
    section("STAGE 0 — Load LingoQA eval split")
    import pyarrow.parquet as pq

    print(f"  val_parquet : {val_parquet}")
    print(f"  images_zip  : {images_zip}")

    table = pq.read_table(val_parquet)
    print(f"  raw rows    : {table.num_rows}")

    # Group 2 annotator rows per question_id into one sample
    grouped: dict[str, dict[str, Any]] = {}
    for i in range(table.num_rows):
        qid = table["question_id"][i].as_py()
        if qid not in grouped:
            grouped[qid] = {
                "question_id": qid,
                "segment_id": table["segment_id"][i].as_py(),
                "question": table["question"][i].as_py(),
                "images": table["images"][i].as_py(),   # list of zip-relative paths
                "answers": [],
            }
        grouped[qid]["answers"].append(table["answer"][i].as_py())

    samples = list(grouped.values())
    print(f"  unique QA   : {len(samples)}")
    print(f"  avg frames  : {sum(len(s['images']) for s in samples) / len(samples):.1f}")
    print(f"  sample Q    : {samples[0]['question']!r}")
    print(f"  sample A[0] : {samples[0]['answers'][0]!r}")
    print(f"  sample A[1] : {samples[0]['answers'][1]!r}")
    print(f"  frame paths : {samples[0]['images'][:2]}")

    # Attach the opened zip handle so inference can read frames lazily
    zf = zipfile.ZipFile(images_zip, "r")
    print(f"  zip entries : {len(zf.namelist())} files")

    return samples, zf


# ---------------------------------------------------------------------------
# Stage 1 — Load model + processor
# ---------------------------------------------------------------------------

def stage1_load_model() -> tuple[Qwen3VLForConditionalGeneration, Qwen3VLProcessor]:
    section("STAGE 1 — Load Cosmos-Reason2-2B")
    print(f"  Model       : {MODEL}")
    print("  torch_dtype : bfloat16  |  device_map: auto")

    model: Qwen3VLForConditionalGeneration = (
        Qwen3VLForConditionalGeneration.from_pretrained(
            MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
    )
    processor: Qwen3VLProcessor = transformers.AutoProcessor.from_pretrained(
        MODEL,
        min_pixels=MIN_PIXELS,
        max_pixels=MAX_PIXELS,
    )

    total_params = sum(p.numel() for p in model.parameters())
    print(f"  total params: {total_params:,}")
    return model, processor


# ---------------------------------------------------------------------------
# Stage 2 — Run inference on all 500 samples
# ---------------------------------------------------------------------------

def _resize_frame(img: PILImage.Image) -> PILImage.Image:
    """Resize frame to fit within MAX_PIXELS, keeping aspect ratio and 32-px multiples.
    Matches Alpamayo 1.5's processor max_pixels=196608 budget.
    min_pixels/max_pixels processor kwargs don't apply to the videos= PIL path in
    Qwen3-VL, so we resize manually before passing to the processor.
    """
    import math
    w, h = img.size
    scale = min(1.0, math.sqrt(MAX_PIXELS / (w * h)))
    new_w = max(32, int(w * scale) // 32 * 32)
    new_h = max(32, int(h * scale) // 32 * 32)
    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), PILImage.LANCZOS)


def _load_frames(zf: zipfile.ZipFile, frame_paths: list[str]) -> list[PILImage.Image]:
    """Load frames from zip, evenly sampling down to MAX_FRAMES, resized to MAX_PIXELS."""
    paths = frame_paths
    if len(paths) > MAX_FRAMES:
        step = len(paths) / MAX_FRAMES
        paths = [paths[int(i * step)] for i in range(MAX_FRAMES)]
    frames = []
    for p in paths:
        try:
            data = zf.read(p)
            frames.append(_resize_frame(PILImage.open(io.BytesIO(data)).convert("RGB")))
        except Exception as e:
            print(f"  WARNING: could not read {p}: {e}")
    return frames


def _run_single(
    model: Qwen3VLForConditionalGeneration,
    processor: Qwen3VLProcessor,
    frames: list[PILImage.Image],
    question: str,
    device: torch.device,
) -> tuple[str, float]:
    """Run one inference. Returns (prediction_text, latency_seconds)."""
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant."}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": frames,
                    "fps": 1.0,
                },
                {"type": "text", "text": question},
            ],
        },
    ]

    text: str = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs: transformers.BatchEncoding = processor(
        text=[text],
        images=None,
        videos=[frames],
        return_tensors="pt",
    ).to(device)

    t0 = time.perf_counter()
    with torch.inference_mode():
        output_ids: torch.Tensor = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
        )
    latency = time.perf_counter() - t0

    prompt_len = inputs["input_ids"].shape[1]
    generated = output_ids[:, prompt_len:]
    prediction: str = processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
    return prediction, latency


def stage2_run_inference(
    samples: list[dict[str, Any]],
    zf: zipfile.ZipFile,
    model: Qwen3VLForConditionalGeneration,
    processor: Qwen3VLProcessor,
    device: torch.device,
) -> list[dict[str, Any]]:
    section("STAGE 2 — Inference (500 samples)")

    results: list[dict[str, Any]] = []
    total = len(samples)

    for i, sample in enumerate(samples):
        frames = _load_frames(zf, sample["images"])
        if not frames:
            print(f"  [{i+1}/{total}] SKIP — no frames loaded")
            continue

        prediction, latency = _run_single(
            model, processor, frames, sample["question"], device
        )

        results.append(
            {
                "question_id": sample["question_id"],
                "question": sample["question"],
                "answers": sample["answers"],
                "prediction": prediction,
                "latency": latency,
                "n_frames": len(frames),
            }
        )

        if (i + 1) % 50 == 0 or i == 0:
            print(
                f"  [{i+1}/{total}]  latency={latency:.2f}s  "
                f"pred={prediction[:60]!r}"
            )

    avg_lat = sum(r["latency"] for r in results) / max(len(results), 1)
    print(f"\n  Done. {len(results)} samples  avg_latency={avg_lat:.2f}s")
    return results


# ---------------------------------------------------------------------------
# Stage 3 — Lingo-Judge scoring
# ---------------------------------------------------------------------------

def stage3_lingo_judge(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    section("STAGE 3 — Lingo-Judge scoring")
    print(f"  model       : {LINGO_JUDGE_MODEL}")
    print(f"  batch_size  : {LINGO_BATCH_SIZE}")
    print("  refs/sample : 2 (take max)")

    from transformers import pipeline

    judge = pipeline(
        "text-classification",
        model=LINGO_JUDGE_MODEL,
        device=0,
        truncation=True,
        max_length=512,
    )

    def _fmt(q: str, ref: str, pred: str) -> str:
        return f"[CLS]\nQuestion: {q}\nAnswer: {ref}\nStudent: {pred}"

    inputs_ref0 = [_fmt(r["question"], r["answers"][0], r["prediction"]) for r in results]
    inputs_ref1 = [_fmt(r["question"], r["answers"][1], r["prediction"]) for r in results]

    print("  Scoring against reference 0 …")
    scores_ref0 = judge(inputs_ref0, batch_size=LINGO_BATCH_SIZE)
    print("  Scoring against reference 1 …")
    scores_ref1 = judge(inputs_ref1, batch_size=LINGO_BATCH_SIZE)

    for r, s0, s1 in zip(results, scores_ref0, scores_ref1):
        r["lingo_score_ref0"] = s0["score"]
        r["lingo_score_ref1"] = s1["score"]
        r["lingo_score"] = max(s0["score"], s1["score"])
        r["lingo_pass"] = r["lingo_score"] > 0.5

    return results


# ---------------------------------------------------------------------------
# Stage 4 — Report
# ---------------------------------------------------------------------------

def stage4_report(results: list[dict[str, Any]]) -> None:
    section("STAGE 4 — Results")

    n = len(results)
    mean_lingo = sum(r["lingo_score"] for r in results) / n
    pass_rate = sum(1 for r in results if r["lingo_pass"]) / n
    avg_latency = sum(r["latency"] for r in results) / n
    avg_frames = sum(r["n_frames"] for r in results) / n

    print(f"  Samples evaluated   : {n}")
    print(f"  Avg frames/clip     : {avg_frames:.1f}")
    print(f"  Avg latency/sample  : {avg_latency:.2f}s")
    print()
    print(f"  Lingo-Judge mean    : {mean_lingo:.4f}")
    print(f"  Lingo-Judge pass    : {pass_rate * 100:.1f}%  (score > 0.5)")
    print()
    print("  (Alpamayo 1.5 reference: 74.2 / 100 on same dataset+metric)")

    print("\n  --- Sample predictions ---")
    for r in results[:5]:
        print(f"  Q   : {r['question'][:80]}")
        print(f"  Ref0: {r['answers'][0][:60]}")
        print(f"  Ref1: {r['answers'][1][:60]}")
        print(f"  Pred: {r['prediction'][:80]}")
        print(f"  Score: {r['lingo_score']:.3f}  pass={r['lingo_pass']}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Cosmos-Reason2-2B on LingoQA")
    parser.add_argument(
        "--val_parquet",
        default="/workspace/data/lingoqa/evaluation/val.parquet",
        help="Path to LingoQA val.parquet",
    )
    parser.add_argument(
        "--images_zip",
        default="/workspace/data/lingoqa/evaluation/evaluation/images.zip",
        help="Path to LingoQA evaluation images.zip",
    )
    args = parser.parse_args()

    print("Cosmos-Reason2-2B × LingoQA Evaluation")
    print(f"torch version       : {torch.__version__}")
    print(f"transformers version: {transformers.__version__}")
    print(f"CUDA available      : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device         : {torch.cuda.get_device_name(0)}")

    samples, zf = stage0_load_dataset(args.val_parquet, args.images_zip)
    model, processor = stage1_load_model()
    device: torch.device = next(model.parameters()).device

    results = stage2_run_inference(samples, zf, model, processor, device)
    zf.close()

    results = stage3_lingo_judge(results)
    stage4_report(results)

    section("DONE")
    print("  Evaluation complete.")


if __name__ == "__main__":
    main()

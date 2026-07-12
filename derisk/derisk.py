"""
derisk/derisk.py

Derisking script for Cosmos-Reason2-2B (Qwen3-VL backbone) inference.
Prints the shape/dtype/content of inputs and outputs at every stage in the pipeline.

Run with:
    bazel run //derisk:derisk
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any


def _preload_cuda_libs() -> None:
    """Pre-load nvidia CUDA .so files before torch is imported.

    torch's libtorch_global_deps.so has RPATH entries of the form
    ``$ORIGIN/../../nvidia/<pkg>/lib`` which assume all nvidia-* wheels
    are siblings in one site-packages directory.  Bazel's pip rules place
    each package in its own isolated directory, so those relative RPATHs
    never resolve.

    The fix: scan sys.path (already populated with Bazel's PYTHONPATH) for
    every ``nvidia/<pkg>/lib/*.so*`` file and load each one with
    RTLD_GLOBAL *before* ctypes touches libtorch_global_deps.so.  Once a
    shared library is mapped into the process, the dynamic linker finds it
    by name even when the RPATH lookup fails.

    This mirrors what torch._preload_cuda_deps() does internally, but
    guarantees it runs before the first import of torch, not conditionally
    inside it.
    """
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

import torch
import transformers
from PIL import Image as PILImage
from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL: str = "nvidia/Cosmos-Reason2-2B"
QUESTION: str = "Describe the driving scene: what objects, road conditions, and hazards do you see?"
SAMPLE_IMAGE_PATH: Path = Path("/tmp/derisk_sample.jpg")
# Street scene with a bus and pedestrians from Ultralytics assets (MIT licence).
# Used as-is in the YOLOv8 test suite — reliable autonomous-driving proxy.
SAMPLE_IMAGE_URL: str = (
    "https://raw.githubusercontent.com/ultralytics/assets/main/im/bus.jpg"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def describe_tensor(name: str, t: torch.Tensor) -> None:
    print(f"  {name}: shape={tuple(t.shape)}  dtype={t.dtype}  device={t.device}")


def describe_batch_encoding(enc: transformers.BatchEncoding) -> None:
    for key, val in enc.items():
        if isinstance(val, torch.Tensor):
            describe_tensor(key, val)
        else:
            print(f"  {key}: type={type(val).__name__}  value={val!r}")


# ---------------------------------------------------------------------------
# Stage 0 — download sample image
# ---------------------------------------------------------------------------

def stage0_download_image() -> Path:
    section("STAGE 0 — Download sample image")
    if not SAMPLE_IMAGE_PATH.exists():
        import ssl
        import urllib.request
        print(f"  Downloading: {SAMPLE_IMAGE_URL}")
        req = urllib.request.Request(SAMPLE_IMAGE_URL, headers={"User-Agent": "derisk/1.0"})
        # Container CA bundles on Jetson are often stale; disable verification for
        # this one-off test download (not production code).
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx) as resp, open(SAMPLE_IMAGE_PATH, "wb") as f:
            f.write(resp.read())
        print(f"  Downloaded OK")
    else:
        print(f"  Reusing cached image")
    img = PILImage.open(SAMPLE_IMAGE_PATH)
    print(f"  Image saved to : {SAMPLE_IMAGE_PATH}")
    print(f"  File size      : {SAMPLE_IMAGE_PATH.stat().st_size:,} bytes")
    print(f"  Dimensions     : {img.size}  mode={img.mode}")
    return SAMPLE_IMAGE_PATH


# ---------------------------------------------------------------------------
# Stage 1 — load model + processor
# ---------------------------------------------------------------------------

def stage1_load_model() -> tuple[Qwen3VLForConditionalGeneration, Qwen3VLProcessor]:
    section("STAGE 1 — Load model and processor")
    print(f"  Model: {MODEL}")
    print(f"  torch_dtype: bfloat16  |  device_map: auto")

    model: Qwen3VLForConditionalGeneration = (
        Qwen3VLForConditionalGeneration.from_pretrained(
            MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
    )
    processor: Qwen3VLProcessor = transformers.AutoProcessor.from_pretrained(MODEL)

    total_params: int = sum(p.numel() for p in model.parameters())
    print(f"\n  model type  : {type(model).__name__}")
    print(f"  total params: {total_params:,}")
    print(f"  vision enc  : {type(model.model.visual).__name__}")
    print(f"  llm backbone: {type(model.model).__name__}")
    print(f"\n  processor type: {type(processor).__name__}")
    return model, processor


# ---------------------------------------------------------------------------
# Stage 2 — build messages dict
# ---------------------------------------------------------------------------

def stage2_build_messages(image_path: Path) -> list[dict[str, Any]]:
    section("STAGE 2 — Build messages list (structured dict)")
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant."}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": f"file://{image_path}",
                },
                {"type": "text", "text": QUESTION},
            ],
        },
    ]

    print(f"  num messages : {len(messages)}")
    for i, msg in enumerate(messages):
        parts: list[str] = [c["type"] for c in msg["content"]]
        print(f"  messages[{i}]  : role={msg['role']}  content_types={parts}")

    print(f"\n  OUTPUT TYPE  : list[dict]")
    print(f"  No pixel data yet — just structured metadata.")
    return messages


# ---------------------------------------------------------------------------
# Stage 3 — apply_chat_template → flat string
# ---------------------------------------------------------------------------

def stage3_apply_chat_template(
    processor: Qwen3VLProcessor,
    messages: list[dict[str, Any]],
) -> str:
    section("STAGE 3 — apply_chat_template → formatted string")
    text: str = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    print(f"  OUTPUT TYPE   : str")
    print(f"  len(text)     : {len(text)} chars")
    print(f"\n  --- text (first 400 chars) ---")
    print(text[:400])
    print(f"  --- text (last 100 chars) ---")
    print(repr(text[-100:]))
    print(f"\n  NOTE: <|vision_start|>...<|vision_end|> is a placeholder;")
    print(f"        pixel data is NOT encoded here yet.")
    return text


# ---------------------------------------------------------------------------
# Stage 4 — processor() → BatchEncoding (tokens + vision patches)
# ---------------------------------------------------------------------------

def stage4_process(
    processor: Qwen3VLProcessor,
    text: str,
    image_path: Path,
    device: torch.device,
) -> transformers.BatchEncoding:
    section("STAGE 4 — processor() → BatchEncoding (token IDs + vision patches)")

    image: PILImage.Image = PILImage.open(image_path).convert("RGB")
    print(f"  PIL image size : {image.size}  mode={image.mode}")

    inputs: transformers.BatchEncoding = processor(
        text=[text],
        images=[image],
        return_tensors="pt",
    ).to(device)

    print(f"\n  OUTPUT TYPE: transformers.BatchEncoding")
    print(f"  Keys: {list(inputs.keys())}")
    print()
    describe_batch_encoding(inputs)

    t, h, w = inputs["image_grid_thw"][0].tolist()
    print(f"\n  image_grid_thw : t={int(t)}  h_patches={int(h)}  w_patches={int(w)}")
    print(f"  resized image  : {int(w)*16}×{int(h)*16} px  (original: {image.size[0]}×{image.size[1]})")
    print(f"  raw patches    : {int(t*h*w)}  →  {int(t*h*w)//4} visual tokens after 2×2 merge")

    print(f"\n  NOTE: input_ids are INTEGER token IDs — not embeddings yet.")
    print(f"        pixel_values are FLOAT patch tensors — vision encoder runs inside model.forward().")

    # Show a snippet of input_ids so we can see special vision tokens
    ids: torch.Tensor = inputs["input_ids"][0]
    print(f"\n  input_ids[:20] : {ids[:20].tolist()}")
    print(f"  input_ids[-10:] : {ids[-10:].tolist()}")
    return inputs


# ---------------------------------------------------------------------------
# Stage 5 — model.generate() → output token IDs
# ---------------------------------------------------------------------------

def stage5_generate(
    model: Qwen3VLForConditionalGeneration,
    inputs: transformers.BatchEncoding,
    max_new_tokens: int = 512,
) -> torch.Tensor:
    section("STAGE 5 — model.generate() → output token IDs")
    print(f"  max_new_tokens : {max_new_tokens}")
    print(f"  Internally: input_ids → embedding table → text embeddings")
    print(f"              pixel_values → ViT (model.visual) → vision embeddings")
    print(f"              splice at <|vision_start|> positions → flat (seq, hidden) tensor")
    print(f"              LLM transformer layers → logits → greedy decode → token IDs")

    with torch.inference_mode():
        output_ids: torch.Tensor = model.generate(**inputs, max_new_tokens=max_new_tokens)

    print(f"\n  OUTPUT TYPE     : torch.Tensor")
    describe_tensor("output_ids", output_ids)
    print(f"  full seq length : {output_ids.shape[1]}  (prompt + generated)")
    print(f"  prompt length   : {inputs['input_ids'].shape[1]}")
    print(f"  new tokens      : {output_ids.shape[1] - inputs['input_ids'].shape[1]}")
    return output_ids


# ---------------------------------------------------------------------------
# Stage 6 — decode → text
# ---------------------------------------------------------------------------

def stage6_decode(
    processor: Qwen3VLProcessor,
    output_ids: torch.Tensor,
    prompt_len: int,
) -> str:
    section("STAGE 6 — processor.batch_decode() → text")
    generated: torch.Tensor = output_ids[:, prompt_len:]
    print(f"  Slicing off prompt tokens: output_ids[:, {prompt_len}:]")
    describe_tensor("generated (sliced)", generated)

    result: str = processor.batch_decode(generated, skip_special_tokens=True)[0]

    print(f"\n  OUTPUT TYPE : str")
    print(f"  len(result) : {len(result)} chars")
    print(f"\n  --- MODEL OUTPUT ---")
    print(result)
    print(f"  --- END ---")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Cosmos-Reason2-2B Derisking Script")
    print(f"torch version       : {torch.__version__}")
    print(f"transformers version: {transformers.__version__}")
    print(f"CUDA available      : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device         : {torch.cuda.get_device_name(0)}")

    image_path: Path = stage0_download_image()
    model, processor = stage1_load_model()
    device: torch.device = next(model.parameters()).device

    messages: list[dict[str, Any]] = stage2_build_messages(image_path)
    text: str = stage3_apply_chat_template(processor, messages)
    inputs: transformers.BatchEncoding = stage4_process(processor, text, image_path, device)
    output_ids: torch.Tensor = stage5_generate(model, inputs)
    prompt_len: int = inputs["input_ids"].shape[1]
    stage6_decode(processor, output_ids, prompt_len)

    section("DONE")
    print("  All stages passed.")


if __name__ == "__main__":
    main()

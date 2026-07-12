"""
runtimes/hf_transformers/runtime.py

HuggingFace Transformers runtime adapter for Cosmos-Reason2-2B.
Runs Qwen3VL inference with native video tokenization (up to 8 evenly-sampled
frames, temporal position embeddings via the "video" content type).

Forward-only: imports only from lib/, models/, runtimes/base, inputs/.
"""

import ctypes
import os
import sys
import time
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase

_LINGO_JUDGE_MODEL = "wayveai/Lingo-Judge"
_LINGO_BATCH_SIZE  = 64


def _preload_cuda_libs() -> None:
    """Pre-load nvidia CUDA .so files before torch imports them.

    Bazel isolates each nvidia-* wheel in its own directory, breaking the
    relative RPATHs that libtorch_global_deps.so expects. Loading every
    nvidia/<pkg>/lib/*.so with RTLD_GLOBAL before torch is imported lets
    the dynamic linker find them by name.

    cuDNN is skipped: torch bundles its own cuDNN and a pip-installed
    nvidia-cudnn conflicts with it (CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH
    on Conv3d).
    """
    for path in sys.path:
        nvidia_dir = os.path.join(path, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        for pkg in os.listdir(nvidia_dir):
            if pkg == "cudnn":
                continue
            lib_dir = os.path.join(nvidia_dir, pkg, "lib")
            if not os.path.isdir(lib_dir):
                continue
            for fname in os.listdir(lib_dir):
                if ".so" not in fname:
                    continue
                try:
                    ctypes.CDLL(os.path.join(lib_dir, fname), mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


_preload_cuda_libs()

import transformers  # noqa: E402 — must follow preload  # type: ignore[import]
from transformers import Qwen3VLForConditionalGeneration  # noqa: E402  # type: ignore[import]


def _run_lingo_judge(results: list[dict]) -> dict:
    """Score all predictions with Lingo-Judge; return mean and pass rate."""
    from transformers import pipeline  # type: ignore[import]

    judge = pipeline(
        "text-classification",
        model=_LINGO_JUDGE_MODEL,
        device=0,
        truncation=True,
        max_length=512,
    )

    def _fmt(q: str, ref: str, pred: str) -> str:
        return f"[CLS]\nQuestion: {q}\nAnswer: {ref}\nStudent: {pred}"

    s0 = judge(
        [_fmt(r["question"], r["answers"][0], r["prediction"]) for r in results],
        batch_size=_LINGO_BATCH_SIZE,
    )
    s1 = judge(
        [_fmt(r["question"], r["answers"][1], r["prediction"]) for r in results],
        batch_size=_LINGO_BATCH_SIZE,
    )

    scores = [max(a["score"], b["score"]) for a, b in zip(s0, s1)]
    mean   = sum(scores) / len(scores)
    rate   = sum(1 for s in scores if s > 0.5) / len(scores)
    return {"lingo_judge_mean": round(mean, 4), "lingo_judge_pass_rate": round(rate, 4)}


class HFTransformersRuntime(RuntimeBase):
    """Qwen3VL inference via HuggingFace Transformers with native video tokenization."""

    SUPPORTED_PRECISIONS: frozenset[str] = frozenset({"bf16"})

    def __init__(self) -> None:
        self._cached_results: list[dict] = []

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Load Qwen3VLForConditionalGeneration and processor. Returns (model, processor)."""
        from models.cosmos_reason2b import spec

        L.info("hf_transformers.init", model=spec.HF_MODEL_ID, precision=precision)

        model = Qwen3VLForConditionalGeneration.from_pretrained(
            spec.HF_MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
        processor = transformers.AutoProcessor.from_pretrained(
            spec.HF_MODEL_ID,
            min_pixels=spec.MIN_PIXELS,
            max_pixels=spec.MAX_PIXELS,
        )
        L.info("hf_transformers.init.done", params=sum(p.numel() for p in model.parameters()))
        return model, processor

    def run(self, handle: Any, input_data: Any, n_iters: int) -> list[float]:
        """
        Run inference on n_iters samples from the LingoQA dataset.

        input_data: (samples, zf) from lingoqa.load()
        n_iters: number of samples to run (WARMUP_ITERS or MEASURE_ITERS)
        Returns per-sample latency in ms. Caches predictions for accuracy().
        """
        from inputs import lingoqa
        from models.cosmos_reason2b import spec

        model, processor = handle
        samples, zf = input_data
        device = next(model.parameters()).device
        self._cached_results = []

        latencies: list[float] = []
        for sample in samples[:n_iters]:
            frames = lingoqa.load_frames(zf, sample["frame_paths"])
            if not frames:
                continue

            messages = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "You are a helpful assistant."}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "video", "video": frames, "fps": 1.0},
                        {"type": "text",  "text": sample["question"]},
                    ],
                },
            ]

            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = processor(
                text=[text], images=None, videos=[frames], return_tensors="pt"
            ).to(device)

            torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.inference_mode():
                output_ids = model.generate(**inputs, max_new_tokens=spec.MAX_NEW_TOKENS)
            torch.cuda.synchronize()
            latencies.append((time.perf_counter() - t0) * 1000.0)

            prompt_len = inputs["input_ids"].shape[1]
            prediction = processor.batch_decode(
                output_ids[:, prompt_len:], skip_special_tokens=True
            )[0].strip()

            self._cached_results.append({
                "question":   sample["question"],
                "answers":    sample["answers"],
                "prediction": prediction,
            })

        return latencies

    def accuracy(self, handle: Any) -> dict | None:
        """Run Lingo-Judge over predictions cached during run(). Returns score dict."""
        if not self._cached_results:
            return None
        L.info("hf_transformers.accuracy.lingo_judge", n=len(self._cached_results))
        return _run_lingo_judge(self._cached_results)

    def teardown(self, handle: Any) -> None:
        """Delete model and processor; free CUDA memory."""
        del handle
        self._cached_results = []
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return installed transformers version."""
        return transformers.__version__

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """Not supported for VLMs. Returns None."""
        return None

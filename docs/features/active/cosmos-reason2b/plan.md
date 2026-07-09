# Plan: Cosmos-Reason2-2B Benchmark Integration

Date: 2026-07-09
Status: awaiting approval

---

## What we are doing

Add Cosmos-Reason2-2B (VLM) to the benchmark harness with two runtimes:

1. **hf_transformers** — HuggingFace Transformers, Qwen3VL, native video tokenization
2. **trt_edge_llm** — TensorRT Edge-LLM C++ engine via pybind11, native temporal pairs

Both are new runtime implementations that follow the same `init/run/teardown/version/profile`
pattern as `pytorch` and `tensorrt`. No wrapping of derisk scripts.

Metrics:
- **Latency**: p50 / p99 per sample (ms), throughput (samples/s) — same as today
- **Accuracy**: Lingo-Judge mean score and pass rate on LingoQA 500-sample eval

Baseline numbers from derisk runs:

| Runtime | Lingo-Judge pass | p50 latency |
|---|---|---|
| hf_transformers | 57.4% | ~770 ms |
| trt_edge_llm | 56.6% | ~550 ms |
| Alpamayo 1.5 (reference) | 74.2% | — |

---

## What changes and what does not

**No changes to:**
- `benchmark/runner.py` core loop (explained below — it works as-is)
- `inputs/imagenet.py`, `inputs/dinov2_input.py`
- Existing runtimes
- `hardware/`
- `lib/`

**New files:**
```
inputs/lingoqa.py
models/cosmos_reason2b/spec.py
models/cosmos_reason2b/BUILD
runtimes/hf_transformers/runtime.py
runtimes/hf_transformers/BUILD
runtimes/trt_edge_llm/runtime.py
runtimes/trt_edge_llm/BUILD
```

**Edited files:**
```
runtimes/base.py              — add optional accuracy() method
benchmark/registry.py         — register new model + runtimes
benchmark/runner.py           — call accuracy() after run(), add fields to result JSON
tools/validate_results.py     — allow two new optional fields in schema
docs/RUNTIMES.md              — add two rows
docs/MODELS.md                — add one row
versions.toml                 — add two runtime entries
site/build.py                 — group by task, add VLM section
site/templates/index.html     — VLM table with Lingo-Judge columns
```

---

## How the existing runner structure handles VLMs

The runner currently does:

```python
input_tensor = input_module.load(model_spec.sample_image_path())
handle = runtime.init(model_path, precision, device)
runtime.run(handle, input_tensor, WARMUP_ITERS)        # warmup
latencies = runtime.run(handle, input_tensor, MEASURE_ITERS)  # measure
p50 = percentile(latencies, 50)
runtime.teardown(handle)
write_result_json(...)
```

For VLMs, `input_module.load()` returns the dataset (500 samples + zip handle)
instead of a tensor. The runtime's `run()` iterates the samples internally,
runs one inference per sample per iter, and returns per-sample latencies.
`n_iters` maps to the number of samples to run, not the number of times to
repeat the same input.

The runner also calls a new optional `accuracy(handle) -> dict | None` method
after `run()`. VLM runtimes cache predictions during `run()`, then score them
with Lingo-Judge inside `accuracy()`. The returned dict is merged into the
result JSON.

Everything else in the runner is unchanged.

---

## Step 1 — LingoQA input pipeline (`inputs/lingoqa.py`)

Follows the same module pattern as `inputs/imagenet.py`.

```python
"""
inputs/lingoqa.py

LingoQA video-QA dataset loader.
Returns a list of sample dicts + an open ZipFile for frame loading.

Input key: "lingoqa"
Used by: models/cosmos_reason2b
"""

import io
import math
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image as PILImage  # type: ignore[import]

VAL_PARQUET = Path("/workspace/data/lingoqa/evaluation/val.parquet")
IMAGES_ZIP  = Path("/workspace/data/lingoqa/evaluation/evaluation/images.zip")
MAX_FRAMES  = 8
MAX_PIXELS  = 196_608   # 512×384 — matches Alpamayo 1.5 eval protocol
MIN_PIXELS  = 163_840


def load(unused_image_path: Path = VAL_PARQUET) -> tuple[list[dict], zipfile.ZipFile]:
    """
    Load LingoQA eval split.

    Returns (samples, zf) where samples is a list of 500 dicts:
        {question_id, question, answers: [str, str], frame_paths: [str, ...]}
    and zf is an open ZipFile for reading frames.
    """
    import pyarrow.parquet as pq  # type: ignore[import]

    table = pq.read_table(VAL_PARQUET)
    grouped: dict[str, dict[str, Any]] = {}
    for i in range(table.num_rows):
        qid = table["question_id"][i].as_py()
        if qid not in grouped:
            grouped[qid] = {
                "question_id": qid,
                "question": table["question"][i].as_py(),
                "frame_paths": table["images"][i].as_py(),
                "answers": [],
            }
        grouped[qid]["answers"].append(table["answer"][i].as_py())

    zf = zipfile.ZipFile(IMAGES_ZIP, "r")
    return list(grouped.values()), zf


def resize_frame(img: PILImage.Image) -> PILImage.Image:
    """Resize to MAX_PIXELS budget, 32-px aligned — matches Alpamayo 1.5."""
    w, h = img.size
    scale = min(1.0, math.sqrt(MAX_PIXELS / (w * h)))
    new_w = max(32, int(w * scale) // 32 * 32)
    new_h = max(32, int(h * scale) // 32 * 32)
    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), PILImage.LANCZOS)


def load_frames(zf: zipfile.ZipFile, frame_paths: list[str]) -> list[PILImage.Image]:
    """Evenly sample up to MAX_FRAMES frames from a clip, resized to MAX_PIXELS."""
    paths = frame_paths
    if len(paths) > MAX_FRAMES:
        step = len(paths) / MAX_FRAMES
        paths = [paths[int(i * step)] for i in range(MAX_FRAMES)]
    frames = []
    for p in paths:
        try:
            data = zf.read(p)
            frames.append(resize_frame(PILImage.open(io.BytesIO(data)).convert("RGB")))
        except Exception:  # noqa: BLE001
            pass
    return frames
```

`load()` takes a `Path` argument to satisfy the runner's `input_module.load(model_spec.sample_image_path())` call. The argument is unused — the path is hardcoded to the LingoQA dataset.

---

## Step 2 — Model spec (`models/cosmos_reason2b/spec.py`)

Same structure as `models/resnet50/spec.py` and `models/dinov2_b/spec.py`.

```python
"""
models/cosmos_reason2b/spec.py

Model spec for Cosmos-Reason2-2B (Qwen3-VL backbone).
Task: video_qa — evaluated on LingoQA with Lingo-Judge.
"""

from pathlib import Path

NAME = "cosmos_reason2b"
TASK = "video_qa"
INPUT_KEY = "lingoqa"
ACTIVE_PRECISION = "bf16"
SUPPORTED_PRECISIONS = ["bf16"]
EXCLUDED_RUNTIMES: frozenset[str] = frozenset()

WARMUP_ITERS = 5        # 5 samples; VLM init is expensive
MEASURE_ITERS = 500     # full LingoQA eval set

# Model identifiers
HF_MODEL_ID = "nvidia/Cosmos-Reason2-2B"
TRT_LLM_ENGINE_DIR    = "/workspace/models/cosmos-reason2-2b-engine/llm"
TRT_VISUAL_ENGINE_DIR = "/workspace/models/cosmos-reason2-2b-engine/visual"

# Generation config — same as derisk eval
MAX_NEW_TOKENS   = 64
MIN_PIXELS       = 163_840
MAX_PIXELS       = 196_608

# Lingo-Judge config
LINGO_JUDGE_MODEL      = "wayveai/Lingo-Judge"
LINGO_JUDGE_BATCH_SIZE = 64


def sample_image_path() -> Path:
    # Unused for VLMs — lingoqa.load() ignores this arg.
    # Required by runner interface.
    return Path(__file__).parent / "sample_frame.jpg"
```

`TASK = "video_qa"` is the flag the runner uses to switch to the VLM code path.

---

## Step 3 — RuntimeBase extension (`runtimes/base.py`)

Add one optional method. All existing runtimes inherit the default (returns `None`).

```python
def accuracy(self, handle: Any) -> dict | None:
    """
    Return accuracy metrics computed over predictions cached during run().
    Called by the runner after run() completes, before teardown().
    Return None if this runtime does not support accuracy evaluation.

    VLM runtimes return a dict, e.g.:
        {"lingo_judge_mean": 0.543, "lingo_judge_pass_rate": 0.566}
    """
    return None
```

Also add `"bf16"` to `PRECISION_TO_DTYPE`:

```python
PRECISION_TO_DTYPE: dict[str, torch.dtype] = {
    "fp32": torch.float32,
    "fp16": torch.float16,
    "bf16": torch.bfloat16,
}
```

---

## Step 4 — HF Transformers runtime (`runtimes/hf_transformers/runtime.py`)

New implementation. Same file structure as `runtimes/pytorch/runtime.py`.

```python
"""
runtimes/hf_transformers/runtime.py

HuggingFace Transformers runtime adapter for Cosmos-Reason2-2B.
Runs Qwen3VL inference with native video tokenization (8 evenly-sampled
frames, temporal position embeddings via the "video" content type).

Forward-only: imports only from lib/, models/, runtimes/base, inputs/.
"""

import ctypes
import io
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase


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
from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor  # type: ignore[import]

from inputs import lingoqa  # noqa: E402

_LINGO_JUDGE_MODEL = "wayveai/Lingo-Judge"
_LINGO_BATCH_SIZE  = 64


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

    s0 = judge([_fmt(r["question"], r["answers"][0], r["prediction"]) for r in results],
               batch_size=_LINGO_BATCH_SIZE)
    s1 = judge([_fmt(r["question"], r["answers"][1], r["prediction"]) for r in results],
               batch_size=_LINGO_BATCH_SIZE)

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
                {"role": "system",
                 "content": [{"type": "text", "text": "You are a helpful assistant."}]},
                {"role": "user",
                 "content": [
                     {"type": "video", "video": frames, "fps": 1.0},
                     {"type": "text",  "text": sample["question"]},
                 ]},
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
                from models.cosmos_reason2b import spec
                output_ids = model.generate(**inputs, max_new_tokens=spec.MAX_NEW_TOKENS)
            torch.cuda.synchronize()
            latencies.append((time.perf_counter() - t0) * 1000.0)

            prompt_len = inputs["input_ids"].shape[1]
            prediction = processor.batch_decode(
                output_ids[:, prompt_len:], skip_special_tokens=True
            )[0].strip()

            self._cached_results.append({
                "question": sample["question"],
                "answers":  sample["answers"],
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

    def profile(self, handle: Any, input_data: Any) -> str | None:
        """Not supported for VLMs. Returns None."""
        return None
```

---

## Step 5 — TRT Edge-LLM runtime (`runtimes/trt_edge_llm/runtime.py`)

New implementation. Same file structure as `runtimes/tensorrt/runtime.py`.

```python
"""
runtimes/trt_edge_llm/runtime.py

TensorRT Edge-LLM runtime adapter for Cosmos-Reason2-2B.
Loads the pre-built LLM + visual TRT engines via the C++ pybind11 module
(_edgellm_runtime) and runs native video inference with temporal frame-pair
fusion (frames processed in pairs through the Conv3d patch embedding).

Forward-only: imports only from lib/, models/, runtimes/base, inputs/.
"""

import ctypes
import importlib.util
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase

_PYBIND_SO_DIR  = Path("/workspace/TensorRT-Edge-LLM/build/pybind")
_PLUGIN_PATH    = Path("/workspace/TensorRT-Edge-LLM/build/libNvInfer_edgellm_plugin.so")
_LINGO_JUDGE_MODEL = "wayveai/Lingo-Judge"
_LINGO_BATCH_SIZE  = 64
_TEMPORAL_PATCH_SIZE = 2  # matches preprocessor_config.json


def _preload_cuda_libs() -> None:
    """Same RPATH fix as hf_transformers; skip cudnn."""
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


def _import_edgellm_rt():
    """Locate and import _edgellm_runtime from the cmake build output."""
    if not os.environ.get("EDGELLM_PLUGIN_PATH"):
        if _PLUGIN_PATH.is_file():
            os.environ["EDGELLM_PLUGIN_PATH"] = str(_PLUGIN_PATH)
        else:
            raise FileNotFoundError(f"Plugin not found: {_PLUGIN_PATH}")

    try:
        from tensorrt_edgellm import _edgellm_runtime as rt  # type: ignore[import]
        return rt
    except ImportError:
        pass

    so_files = list(_PYBIND_SO_DIR.glob("_edgellm_runtime*.so"))
    if not so_files:
        raise ImportError(f"_edgellm_runtime*.so not found in {_PYBIND_SO_DIR}")
    spec = importlib.util.spec_from_file_location("_edgellm_runtime", so_files[0])
    mod  = importlib.util.module_from_spec(spec)
    sys.modules["_edgellm_runtime"] = mod
    spec.loader.exec_module(mod)
    return mod


def _frame_to_jpeg(frame) -> bytes:
    """Encode PIL frame to JPEG bytes for load_image_from_bytes()."""
    buf = io.BytesIO()
    frame.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _build_request(rt, question: str, frames: list, max_tokens: int):
    """
    Build an LLMGenerationRequest using native video temporal-pair fusion.

    8 frames → 4 temporal pairs → 4 image-placeholder content items.
    video_buffers holds all frames; C++ pairs them (frame0+frame1, ...).
    """
    import math
    n_pairs = math.ceil(len(frames) / _TEMPORAL_PATCH_SIZE)

    sys_msg = rt.Message()
    sys_msg.role = "system"
    sys_msg.contents = [rt.MessageContent("text", "You are a helpful assistant.")]

    user_msg = rt.Message()
    user_msg.role = "user"
    contents  = [rt.MessageContent("image", "") for _ in range(n_pairs)]
    contents.append(rt.MessageContent("text", question))
    user_msg.contents = contents

    cpp_req = rt.Request(messages=[sys_msg, user_msg])
    cpp_req.video_buffers = [rt.load_image_from_bytes(_frame_to_jpeg(f)) for f in frames]

    gen_req = rt.LLMGenerationRequest()
    gen_req.requests          = [cpp_req]
    gen_req.max_generate_length = max_tokens
    gen_req.apply_chat_template = True
    gen_req.add_generation_prompt = True
    gen_req.temperature = 1.0
    gen_req.top_p       = 0.8
    gen_req.top_k       = 50
    return gen_req


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

    s0 = judge([_fmt(r["question"], r["answers"][0], r["prediction"]) for r in results],
               batch_size=_LINGO_BATCH_SIZE)
    s1 = judge([_fmt(r["question"], r["answers"][1], r["prediction"]) for r in results],
               batch_size=_LINGO_BATCH_SIZE)

    scores = [max(a["score"], b["score"]) for a, b in zip(s0, s1)]
    mean   = sum(scores) / len(scores)
    rate   = sum(1 for s in scores if s > 0.5) / len(scores)
    return {"lingo_judge_mean": round(mean, 4), "lingo_judge_pass_rate": round(rate, 4)}


class TRTEdgeLLMRuntime(RuntimeBase):
    """Cosmos-Reason2-2B inference via TRT Edge-LLM C++ engine (pybind11)."""

    SUPPORTED_PRECISIONS: frozenset[str] = frozenset({"bf16"})

    def __init__(self) -> None:
        self._cached_results: list[dict] = []

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """
        Load TRT Edge-LLM runtime from pre-built engines.
        Returns (rt_module, runtime_instance).
        """
        _preload_cuda_libs()
        from models.cosmos_reason2b import spec

        L.info("trt_edge_llm.init",
               llm_engine=spec.TRT_LLM_ENGINE_DIR,
               visual_engine=spec.TRT_VISUAL_ENGINE_DIR)

        rt = _import_edgellm_rt()
        runtime = rt.LLMRuntime(
            spec.TRT_LLM_ENGINE_DIR,
            spec.TRT_VISUAL_ENGINE_DIR,
            {},
        )
        runtime.capture_decoding_cuda_graph()
        L.info("trt_edge_llm.init.done")
        return rt, runtime

    def run(self, handle: Any, input_data: Any, n_iters: int) -> list[float]:
        """
        Run inference on n_iters samples from the LingoQA dataset.

        input_data: (samples, zf) from lingoqa.load()
        n_iters: number of samples to run (WARMUP_ITERS or MEASURE_ITERS)
        Returns per-sample latency in ms. Caches predictions for accuracy().
        """
        rt, runtime = handle
        samples, zf = input_data
        self._cached_results = []

        from inputs import lingoqa
        from models.cosmos_reason2b import spec

        latencies: list[float] = []
        for sample in samples[:n_iters]:
            frames = lingoqa.load_frames(zf, sample["frame_paths"])
            if not frames:
                continue

            gen_req = _build_request(rt, sample["question"], frames, spec.MAX_NEW_TOKENS)

            t0 = time.perf_counter()
            response = runtime.handle_request(gen_req)
            latencies.append((time.perf_counter() - t0) * 1000.0)

            prediction = response.output_texts[0].strip() if response.output_texts else ""
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
        L.info("trt_edge_llm.accuracy.lingo_judge", n=len(self._cached_results))
        return _run_lingo_judge(self._cached_results)

    def teardown(self, handle: Any) -> None:
        """Delete runtime handle."""
        del handle
        self._cached_results = []

    def version(self) -> str:
        """Return TRT Edge-LLM version from installed package or fallback."""
        try:
            from tensorrt_edgellm import _version  # type: ignore[import]
            return _version.__version__
        except ImportError:
            return "0.9.0"

    def profile(self, handle: Any, input_data: Any) -> str | None:
        """Not supported. Returns None."""
        return None
```

---

## Step 6 — Runner changes (`benchmark/runner.py`)

Two small additions to `_run_single_benchmark()`:

**1. Pass the raw dataset to `run()` for VLM models:**

```python
# existing:
input_tensor = input_module.load(model_spec.sample_image_path())

# new: load() returns (samples, zf) for VLMs; tensor for vision models
input_data = input_module.load(model_spec.sample_image_path())

# then pass input_data instead of input_tensor everywhere in the function
```

**2. Call `accuracy()` after measurement, add fields to result:**

```python
# after measured_latencies = runtime_instance.run(...)
accuracy_metrics = runtime_instance.accuracy(engine_handle)

# in the result dict:
result = {
    ...,
    "lingo_judge_mean":      accuracy_metrics.get("lingo_judge_mean")      if accuracy_metrics else None,
    "lingo_judge_pass_rate": accuracy_metrics.get("lingo_judge_pass_rate") if accuracy_metrics else None,
    ...,
}
```

No other runner changes. The warmup/measure/percentile/teardown/profile flow is unchanged.

---

## Step 7 — Result JSON schema (`tools/validate_results.py`)

Add two nullable optional fields. They are `None` for all existing models.

```python
"lingo_judge_mean":      {"type": ["number", "null"]},
"lingo_judge_pass_rate": {"type": ["number", "null"]},
```

Example result for `cosmos_reason2b`:

```json
{
  "runtime": "trt_edge_llm",
  "model": "cosmos_reason2b",
  "precision": "bf16",
  "batch_size": 1,
  "latency_ms": {"p50": 550.0, "p99": 890.0},
  "throughput": 1.82,
  "lingo_judge_mean": 0.5430,
  "lingo_judge_pass_rate": 0.566,
  "hw_id": "thor",
  "docker_image": "sha256:...",
  "sw_versions": {
    "trt_edge_llm": "0.9.0",
    "cuda": "13.0",
    "driver": "580.00"
  },
  "timestamp": "2026-07-09T00:00:00Z",
  "status": "ok",
  "profile_file": null
}
```

---

## Step 8 — Website

`site/build.py`: group results by `model_spec.TASK`. Results with `task == "video_qa"`
go into a new "VLM Benchmarks" section. Everything else stays in "Vision Benchmarks".

`site/templates/index.html`: VLM table has columns:

```
Runtime | p50 (ms) | p99 (ms) | Samples/s | Lingo-Judge pass | Lingo-Judge mean | Timestamp | Status
```

---

## Step 9 — Registry, docs, versions

`benchmark/registry.py`:
```python
from inputs import lingoqa
from models.cosmos_reason2b import spec as cosmos_reason2b_spec
from runtimes.hf_transformers.runtime import HFTransformersRuntime
from runtimes.trt_edge_llm.runtime import TRTEdgeLLMRuntime

INPUT_REGISTRY["lingoqa"] = lingoqa
MODEL_REGISTRY["cosmos_reason2b"] = cosmos_reason2b_spec
RUNTIME_REGISTRY["hf_transformers"] = HFTransformersRuntime
RUNTIME_REGISTRY["trt_edge_llm"]    = TRTEdgeLLMRuntime
```

`versions.toml`:
```toml
[runtimes]
hf_transformers = "5.13.0"
trt_edge_llm    = "0.9.0"

[sources]
hf_transformers = "https://github.com/huggingface/transformers/releases"
trt_edge_llm    = "https://github.com/NVIDIA/TensorRT-Edge-LLM/releases"
```

`docs/RUNTIMES.md` — two new rows:
```
| hf_transformers | `//runtimes/hf_transformers` | https://huggingface.co/docs/transformers | active |
| trt_edge_llm    | `//runtimes/trt_edge_llm`    | https://nvidia.github.io/TensorRT-Edge-LLM | active |
```

`docs/MODELS.md` — one new row:
```
| cosmos_reason2b | Video QA (driving) | video + text | `//models/cosmos_reason2b` | BF16 | active |
```

---

## Build order

Each step must pass `//ci:lint` before starting the next.

1. `inputs/lingoqa.py` + BUILD — standalone, no model deps
2. `models/cosmos_reason2b/` + MODELS.md row
3. `runtimes/base.py` — add `accuracy()` stub + `"bf16"` to PRECISION_TO_DTYPE
4. `runtimes/hf_transformers/` + RUNTIMES.md row
5. `runtimes/trt_edge_llm/` + RUNTIMES.md row
6. `benchmark/registry.py` — register all three new entries
7. `benchmark/runner.py` — add `accuracy()` call + result fields
8. `tools/validate_results.py` — allow new optional fields
9. `site/build.py` + `site/templates/index.html` — VLM section
10. `versions.toml` — add new runtime entries
11. `//ci:lint` — full clean pass
12. Manual benchmark run — verify two result JSONs written
13. `//tools:validate_results` — must pass on new JSONs
14. `//site:build` — verify VLM section appears

---

## What we are NOT doing

- No wrappers around derisk scripts
- No Docker changes
- No new `requirement()` Bazel deps for `trt_edge_llm` (pybind `.so` loaded dynamically)
- No INT8/FP8 for VLMs
- No per-layer profiling (`profile()` returns None for both VLM runtimes)
- No streaming, no speculative decoding metrics
- No batch > 1

---

## Open questions

1. **Warmup semantics**: For `trt_edge_llm`, the CUDA graph is captured in `init()` so the first inference is already fast. `WARMUP_ITERS = 5` is conservative. Can reduce to 2 if benchmark time is a concern.
2. **Lingo-Judge GPU**: Lingo-Judge (~0.5 GB) runs on the same GPU as the model (~5 GB). Thor has 28 GB VRAM — both fit. The `accuracy()` call loads Lingo-Judge after the model is already loaded (before `teardown()`). Acceptable.
3. **LingoQA dataset paths**: Hardcoded in `inputs/lingoqa.py`. Move to a config file later if needed.

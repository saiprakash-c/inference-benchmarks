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


from lib import log as L
from runtimes.base import RuntimeBase

_PYBIND_SO_DIR   = Path("/workspace/TensorRT-Edge-LLM/build/pybind")
_PLUGIN_PATH     = Path("/workspace/TensorRT-Edge-LLM/build/libNvInfer_edgellm_plugin.so")
_LINGO_JUDGE_MODEL  = "wayveai/Lingo-Judge"
_LINGO_BATCH_SIZE   = 64
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


def _frame_to_jpeg(frame: Any) -> bytes:
    """Encode PIL frame to JPEG bytes for load_image_from_bytes()."""
    buf = io.BytesIO()
    frame.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _build_request(rt: Any, question: str, frames: list, max_tokens: int) -> Any:
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
    contents = [rt.MessageContent("image", "") for _ in range(n_pairs)]
    contents.append(rt.MessageContent("text", question))
    user_msg.contents = contents

    cpp_req = rt.Request(messages=[sys_msg, user_msg])
    cpp_req.video_buffers = [rt.load_image_from_bytes(_frame_to_jpeg(f)) for f in frames]

    gen_req = rt.LLMGenerationRequest()
    gen_req.requests            = [cpp_req]
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

        L.info(
            "trt_edge_llm.init",
            llm_engine=spec.TRT_LLM_ENGINE_DIR,
            visual_engine=spec.TRT_VISUAL_ENGINE_DIR,
        )

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
        from inputs import lingoqa
        from models.cosmos_reason2b import spec

        rt, runtime = handle
        samples, zf = input_data
        self._cached_results = []

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

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """Not supported. Returns None."""
        return None

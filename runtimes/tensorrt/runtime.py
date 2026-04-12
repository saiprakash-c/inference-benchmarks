"""
runtimes/tensorrt/runtime.py

TensorRT runtime adapter: exports to ONNX, builds a TRT engine (cached),
and runs timed inference using PyTorch CUDA tensors for memory management.
"""

import io
import time
from pathlib import Path
from typing import Any

import tensorrt as trt  # type: ignore[import]
import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import PRECISION_TO_DTYPE, RuntimeBase

TRT_CACHE_DIR = Path("/tmp/trt_cache")

# TensorRT logger that emits warnings and above.
_TRT_LOGGER = trt.Logger(trt.Logger.WARNING)


class TensorRTRuntime(RuntimeBase):
    """Compiles a TRT engine (cached to disk) and runs timed CUDA inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Build or load a cached TRT engine and allocate GPU input/output tensors."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        engine_cache_path = TRT_CACHE_DIR / f"{model_name}_{precision}.engine"

        if engine_cache_path.exists():
            L.info("tensorrt.init.cache_hit", engine_path=str(engine_cache_path))
            engine = _load_engine_from_cache(engine_cache_path)
        else:
            L.info("tensorrt.init.cache_miss", engine_path=str(engine_cache_path))
            onnx_bytes = _export_to_onnx(model_name)
            engine = _build_engine_from_onnx(onnx_bytes, precision)
            _save_engine_to_cache(engine, engine_cache_path)

        context = engine.create_execution_context()

        dtype = PRECISION_TO_DTYPE[precision]
        in_shape = loader.input_shape(model_name)
        out_shape = loader.output_shape(model_name)
        input_gpu_buffer = torch.zeros(*in_shape, dtype=dtype, device="cuda").contiguous()
        output_gpu_buffer = torch.zeros(*out_shape, dtype=dtype, device="cuda").contiguous()

        return {
            "context": context,
            "engine": engine,
            "input_gpu": input_gpu_buffer,
            "output_gpu": output_gpu_buffer,
        }

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Copy input to GPU buffer, execute TRT n_iters times, return latencies in ms."""
        context: Any = handle["context"]
        input_gpu_buffer: torch.Tensor = handle["input_gpu"]
        output_gpu_buffer: torch.Tensor = handle["output_gpu"]

        buf_dtype = input_gpu_buffer.dtype
        gpu_input = input_tensor.to(device="cuda", dtype=buf_dtype)
        input_gpu_buffer.copy_(gpu_input)

        bindings = [input_gpu_buffer.data_ptr(), output_gpu_buffer.data_ptr()]
        latencies: list[float] = []

        for _ in range(n_iters):
            torch.cuda.synchronize()
            start_time = time.perf_counter()
            context.execute_v2(bindings=bindings)
            torch.cuda.synchronize()
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)

        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the TRT context, engine, and GPU buffers."""
        del handle["context"]
        del handle["engine"]
        del handle["input_gpu"]
        del handle["output_gpu"]
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed TensorRT version string."""
        return trt.__version__

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """Attach a SimpleProfiler to the TRT context, run one iteration, return layer table."""
        context: Any = handle["context"]
        input_gpu_buffer: torch.Tensor = handle["input_gpu"]
        output_gpu_buffer: torch.Tensor = handle["output_gpu"]

        buf_dtype = input_gpu_buffer.dtype
        gpu_input = input_tensor.to(device="cuda", dtype=buf_dtype)
        input_gpu_buffer.copy_(gpu_input)
        bindings = [input_gpu_buffer.data_ptr(), output_gpu_buffer.data_ptr()]

        profiler = _TRTProfiler()
        context.profiler = profiler
        torch.cuda.synchronize()
        context.execute_v2(bindings=bindings)
        torch.cuda.synchronize()

        return profiler.to_table()


class _TRTProfiler(trt.IProfiler):
    """Simple IProfiler subclass that records per-layer timing from TensorRT."""

    def __init__(self) -> None:
        super().__init__()
        self._layers: list[tuple[str, float]] = []

    def report_layer_time(self, layer_name: str, ms: float) -> None:  # type: ignore[override]
        self._layers.append((layer_name, ms))

    def to_table(self) -> str:
        if not self._layers:
            return "(no layer timing data recorded)"
        lines = [f"{'Layer':<60}  {'ms':>8}", "-" * 70]
        total = 0.0
        for name, ms in self._layers:
            lines.append(f"{name:<60}  {ms:>8.4f}")
            total += ms
        lines.append("-" * 70)
        lines.append(f"{'TOTAL':<60}  {total:>8.4f}")
        return "\n".join(lines)


def _export_to_onnx(model_name: str) -> bytes:
    """Export model to ONNX bytes in memory using a dummy input."""
    model = loader.load(model_name, device="cpu")
    in_shape = loader.input_shape(model_name)
    dummy_input = torch.zeros(*in_shape, dtype=torch.float32)

    onnx_buffer = io.BytesIO()
    torch.onnx.export(
        model,
        dummy_input,
        onnx_buffer,
        opset_version=18,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes=None,
    )
    return onnx_buffer.getvalue()


def _build_engine_from_onnx(onnx_bytes: bytes, precision: str) -> Any:
    """Parse ONNX bytes and build a TensorRT ICudaEngine."""
    builder = trt.Builder(_TRT_LOGGER)
    network_flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(network_flags)
    parser = trt.OnnxParser(network, _TRT_LOGGER)

    if not parser.parse(onnx_bytes):
        errors = [str(parser.get_error(i)) for i in range(parser.num_errors)]
        raise RuntimeError(f"TensorRT ONNX parsing failed: {errors}")

    build_config = builder.create_builder_config()
    build_config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)  # 1 GiB
    if PRECISION_TO_DTYPE[precision] == torch.float16:
        build_config.set_flag(trt.BuilderFlag.FP16)

    serialized_engine = builder.build_serialized_network(network, build_config)
    if serialized_engine is None:
        raise RuntimeError("TensorRT engine build failed: build_serialized_network returned None")

    runtime = trt.Runtime(_TRT_LOGGER)
    engine = runtime.deserialize_cuda_engine(serialized_engine)
    if engine is None:
        raise RuntimeError("TensorRT engine deserialization failed")

    return engine


def _save_engine_to_cache(engine: Any, cache_path: Path) -> None:
    """Serialize and write the TRT engine to disk at cache_path."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(engine.serialize())
    L.info("tensorrt.cache.saved", path=str(cache_path))


def _load_engine_from_cache(cache_path: Path) -> Any:
    """Deserialize a TRT engine from a cached file on disk."""
    runtime = trt.Runtime(_TRT_LOGGER)
    engine = runtime.deserialize_cuda_engine(cache_path.read_bytes())
    if engine is None:
        raise RuntimeError(f"TensorRT engine deserialization from cache failed: {cache_path}")
    return engine

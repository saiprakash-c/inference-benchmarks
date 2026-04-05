"""
runtimes/tensorrt/runtime.py

TensorRT runtime adapter: exports ResNet50 to ONNX, builds a TRT engine,
caches the compiled engine to disk, and runs timed inference via CUDA buffers.
"""

import io
import os
import time
from pathlib import Path
from typing import Any

import numpy as np  # type: ignore[import]
import tensorrt as trt  # type: ignore[import]
import torch  # type: ignore[import]
import torchvision.models as tv_models  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase

TRT_CACHE_DIR = Path("/tmp/trt_cache")

# TensorRT logger that emits warnings and above.
_TRT_LOGGER = trt.Logger(trt.Logger.WARNING)


class TensorRTRuntime(RuntimeBase):
    """Compiles a ResNet50 TRT engine (cached to disk) and runs timed CUDA inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """
        Build or load a cached TRT engine for model_path at the given precision.
        Returns a tuple (context, input_binding, output_binding) ready for execute_v2.
        """
        model_name = Path(model_path).stem if model_path else "resnet50"
        engine_cache_path = TRT_CACHE_DIR / f"{model_name}_{precision}.engine"

        if engine_cache_path.exists():
            L.info("tensorrt.init.cache_hit", engine_path=str(engine_cache_path))
            engine = _load_engine_from_cache(engine_cache_path)
        else:
            L.info("tensorrt.init.cache_miss", engine_path=str(engine_cache_path))
            onnx_bytes = _export_resnet50_to_onnx(precision)
            engine = _build_engine_from_onnx(onnx_bytes, precision)
            _save_engine_to_cache(engine, engine_cache_path)

        context = engine.create_execution_context()

        # Allocate pinned host buffers and CUDA device buffers for input and output.
        input_shape = (1, 3, 224, 224)
        output_shape = (1, 1000)

        input_host_buffer = np.zeros(input_shape, dtype=np.float32)
        output_host_buffer = np.zeros(output_shape, dtype=np.float32)

        import pycuda.driver as cuda  # type: ignore[import]
        import pycuda.autoinit  # type: ignore[import]  # noqa: F401

        input_device_buffer = cuda.mem_alloc(input_host_buffer.nbytes)
        output_device_buffer = cuda.mem_alloc(output_host_buffer.nbytes)

        return {
            "context": context,
            "engine": engine,
            "input_host": input_host_buffer,
            "output_host": output_host_buffer,
            "input_device": input_device_buffer,
            "output_device": output_device_buffer,
        }

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """
        Copy input to GPU buffer, execute the TRT engine n_iters times, return latencies in ms.
        """
        import pycuda.driver as cuda  # type: ignore[import]

        context: Any = handle["context"]
        input_host: np.ndarray = handle["input_host"]
        output_host: np.ndarray = handle["output_host"]
        input_device: Any = handle["input_device"]
        output_device: Any = handle["output_device"]

        # Convert tensor to numpy and copy into pinned host buffer.
        numpy_input = input_tensor.numpy() if not input_tensor.is_cuda else input_tensor.cpu().numpy()
        np.copyto(input_host, numpy_input)

        bindings = [int(input_device), int(output_device)]
        latencies: list[float] = []

        for _ in range(n_iters):
            cuda.memcpy_htod(input_device, input_host)
            start_time = time.perf_counter()
            context.execute_v2(bindings=bindings)
            cuda.Context.synchronize()
            end_time = time.perf_counter()
            cuda.memcpy_dtoh(output_host, output_device)
            latencies.append((end_time - start_time) * 1000.0)

        return latencies

    def teardown(self, handle: Any) -> None:
        """Free CUDA device buffers and delete the TRT context and engine."""
        handle["input_device"].free()
        handle["output_device"].free()
        del handle["context"]
        del handle["engine"]

    def version(self) -> str:
        """Return the installed TensorRT version string."""
        return trt.__version__


def _export_resnet50_to_onnx(precision: str) -> bytes:
    """Export a torchvision ResNet50 model to ONNX bytes in memory."""
    weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
    model = tv_models.resnet50(weights=weights)
    model.eval()

    dummy_input = torch.zeros(1, 3, 224, 224, dtype=torch.float32)
    onnx_buffer = io.BytesIO()

    torch.onnx.export(
        model,
        dummy_input,
        onnx_buffer,
        opset_version=17,
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
        errors = [str(parser.get_error(index)) for index in range(parser.num_errors)]
        raise RuntimeError(f"TensorRT ONNX parsing failed: {errors}")

    build_config = builder.create_builder_config()
    build_config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)  # 1 GiB

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
    serialized = engine.serialize()
    cache_path.write_bytes(serialized)
    L.info("tensorrt.cache.saved", path=str(cache_path))


def _load_engine_from_cache(cache_path: Path) -> Any:
    """Deserialize a TRT engine from a cached file on disk."""
    runtime = trt.Runtime(_TRT_LOGGER)
    engine_bytes = cache_path.read_bytes()
    engine = runtime.deserialize_cuda_engine(engine_bytes)
    if engine is None:
        raise RuntimeError(f"TensorRT engine deserialization from cache failed: {cache_path}")
    return engine

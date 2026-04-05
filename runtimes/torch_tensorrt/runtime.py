"""
runtimes/torch_tensorrt/runtime.py

Torch-TensorRT runtime adapter: compiles the model directly from a PyTorch
module using torch_tensorrt.compile() (the Dynamo path) — no ONNX export
required. The compiled module is cached to disk as a TorchScript .pt file
and reloaded on subsequent runs.

Advantages over the ONNX→TRT path:
  - No ONNX intermediate: Dynamo traces the graph natively
  - Full op coverage: anything PyTorch supports is automatically handled
  - Consistent with how torch.compile() works: same graph capture semantics
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import PRECISION_TO_DTYPE, RuntimeBase

TORCH_TRT_CACHE_DIR = Path("/tmp/torch_trt_cache")


class TorchTensorRTRuntime(RuntimeBase):
    """Compiles a model via Torch-TensorRT Dynamo backend (cached) and runs timed CUDA inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Compile model via torch_tensorrt.compile() (cached as .ep), return callable."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        cache_path = TORCH_TRT_CACHE_DIR / f"{model_name}_{precision}.ep"

        dtype = PRECISION_TO_DTYPE[precision]
        in_shape = loader.input_shape(model_name)
        dummy_input = torch.zeros(*in_shape, dtype=dtype, device=device)

        if cache_path.exists():
            L.info("torch_tensorrt.init.cache_hit", path=str(cache_path))
            import torch_tensorrt  # type: ignore[import]
            ep = torch_tensorrt.load(str(cache_path))
            runner = ep.module()
        else:
            L.info("torch_tensorrt.init.cache_miss", path=str(cache_path))
            runner = _compile_and_cache(model_name, cache_path, dummy_input, dtype, device)

        return {"runner": runner, "dtype": dtype, "device": device, "dummy": dummy_input}

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times with CUDA-synchronised timing; return latencies in ms."""
        device_tensor = input_tensor.to(device=handle["device"], dtype=handle["dtype"])
        runner = handle["runner"]
        latencies: list[float] = []
        for _ in range(n_iters):
            torch.cuda.synchronize()
            start_time = time.perf_counter()
            runner(device_tensor)
            torch.cuda.synchronize()
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Release runner and CUDA memory."""
        del handle["runner"]
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed torch_tensorrt version string."""
        import torch_tensorrt  # type: ignore[import]
        return torch_tensorrt.__version__


def _compile_and_cache(
    model_name: str,
    cache_path: Path,
    dummy_input: torch.Tensor,
    dtype: torch.dtype,
    device: str,
) -> Any:
    """Compile model via Torch-TensorRT Dynamo backend, save ExportedProgram, return runner."""
    import torch_tensorrt  # type: ignore[import]

    model = loader.load(model_name, device).to(dtype=dtype)

    # torch_tensorrt.compile() uses torch.export + the TRT Dynamo backend.
    # enabled_precisions controls which TRT kernels are allowed: {torch.float32}
    # forces all-fp32, {torch.float16} enables fp16 (TRT picks fp16 kernels).
    # truncate_long_and_double: safe cast of any int64→int32 TRT doesn't support.
    # use_explicit_typing=False: allow enabled_precisions to drive kernel selection.
    # In torch_tensorrt 2.11, use_explicit_typing defaults to True for dynamo IR,
    # which conflicts with enabled_precisions — override it here.
    compiled = torch_tensorrt.compile(
        model,
        ir="dynamo",
        inputs=[dummy_input],
        enabled_precisions={dtype},
        truncate_long_and_double=True,
        use_explicit_typing=False,
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    torch_tensorrt.save(compiled, str(cache_path), inputs=[dummy_input])
    L.info("torch_tensorrt.cache.saved", path=str(cache_path))

    return compiled.module()

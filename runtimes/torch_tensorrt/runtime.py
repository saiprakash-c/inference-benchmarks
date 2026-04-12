"""
runtimes/torch_tensorrt/runtime.py

Torch-TensorRT runtime adapter: compiles the model directly from a PyTorch
module using torch_tensorrt.compile() (the Dynamo path) — no ONNX export
required. The compiled GraphModule is cached to disk as a .ep file and
reloaded on subsequent runs.

Advantages over the ONNX→TRT path:
  - No ONNX intermediate: Dynamo traces the graph natively
  - Full op coverage: anything PyTorch supports is automatically handled
  - Consistent with how torch.compile() works: same graph capture semantics

Notes on torch_tensorrt 2.11 API:
  - torch_tensorrt.compile(ir="dynamo") returns a torch.fx.GraphModule
  - torch_tensorrt.save() serialises it to an ExportedProgram (.ep)
  - torch_tensorrt.load() returns an ExportedProgram; .module() gives the callable
  - use_explicit_typing defaults to True in 2.11 for dynamo IR — must set False
    to allow enabled_precisions to drive kernel selection
  - SDPA ops (scaled_dot_product_attention) are not TRT-convertible; pass via
    torch_executed_ops so they run in PyTorch (hybrid graph)
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import PRECISION_TO_DTYPE, RuntimeBase

TORCH_TRT_CACHE_DIR = Path("/tmp/torch_trt_cache")

# Attention ops TRT cannot lower — run them in PyTorch (hybrid execution).
_TORCH_EXECUTED_OPS: set[str] = {
    "torch.ops.aten._scaled_dot_product_efficient_attention.default",
    "torch.ops.aten._scaled_dot_product_flash_attention.default",
    "torch.ops.aten.scaled_dot_product_attention.default",
}


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
            # load() returns an ExportedProgram; .module() gives the callable GraphModule.
            ep = torch_tensorrt.load(str(cache_path))
            runner = ep.module()
        else:
            L.info("torch_tensorrt.init.cache_miss", path=str(cache_path))
            runner = _compile_and_cache(model_name, cache_path, dummy_input, dtype, device)

        return {"runner": runner, "dtype": dtype, "device": device}

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


class _ForwardWrapper(torch.nn.Module):
    """
    Wraps a model in a clean forward(self, x) → Tensor signature.

    Required for models like DINOv2-B whose ViT forward uses *args — torch_tensorrt's
    dynamic_shapes inference mismatches tuple vs dict when it sees *args. A wrapper
    with an explicit positional parameter eliminates the mismatch.
    """

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


def _compile_and_cache(
    model_name: str,
    cache_path: Path,
    dummy_input: torch.Tensor,
    dtype: torch.dtype,
    device: str,
) -> Any:
    """Compile model via Torch-TensorRT Dynamo backend, save ExportedProgram, return runner."""
    import torch_tensorrt  # type: ignore[import]

    raw_model = loader.load(model_name, device).to(dtype=dtype)
    model = _ForwardWrapper(raw_model)

    # compile() returns a torch.fx.GraphModule (NOT ExportedProgram).
    # use_explicit_typing=False: required to use enabled_precisions in 2.11+.
    # torch_executed_ops: SDPA variants aren't TRT-lowerable; run them in PyTorch.
    compiled = torch_tensorrt.compile(
        model,
        ir="dynamo",
        inputs=[dummy_input],
        enabled_precisions={dtype},
        truncate_long_and_double=True,
        use_explicit_typing=False,
        torch_executed_ops=_TORCH_EXECUTED_OPS,
    )
    # compiled is a GraphModule — callable directly, no .module() needed.

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        torch_tensorrt.save(compiled, str(cache_path), inputs=[dummy_input])
        L.info("torch_tensorrt.cache.saved", path=str(cache_path))
    except Exception as exc:  # noqa: BLE001
        # Flash attention (fp16) outputs torch.uint64 tensors internally; the EP
        # serializer doesn't support that dtype. Skip cache — model still runs.
        L.warn("torch_tensorrt.cache.save_skipped", reason=str(exc)[:120])

    return compiled

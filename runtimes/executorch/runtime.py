"""
runtimes/executorch/runtime.py

ExecuTorch runtime adapter:
  - device="cuda": lowers via CudaPartitioner (AOTInductor-backed), runs on GPU.
  - device="cpu":  lowers via XnnpackPartitioner, runs on CPU.

Compiled .pte programs are cached to disk.
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]
import torchvision.models as tv_models  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase

ET_CACHE_DIR = Path("/tmp/et_cache")


class ExecuTorchRuntime(RuntimeBase):
    """Exports ResNet50 with the CUDA or XNNPACK delegate and runs timed inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Export ResNet50 to a .pte file (cached), load and return a (executor, device) pair."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        suffix = "cuda" if device == "cuda" else "cpu"
        pte_path = ET_CACHE_DIR / f"{model_name}_{precision}_{suffix}.pte"

        if pte_path.exists():
            L.info("executorch.init.cache_hit", pte_path=str(pte_path), device=device)
        else:
            L.info("executorch.init.cache_miss", pte_path=str(pte_path), device=device)
            if device == "cuda":
                _export_and_cache_cuda(pte_path)
            else:
                _export_and_cache_xnnpack(pte_path)

        from executorch.extension.pybindings.portable_lib import (  # type: ignore[import]
            _load_for_executorch,
        )

        executor = _load_for_executorch(str(pte_path))
        return {"executor": executor, "device": device}

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times; return latencies in ms."""
        executor = handle["executor"]
        device = handle["device"]

        if device == "cuda":
            run_input = input_tensor.cuda() if not input_tensor.is_cuda else input_tensor
        else:
            run_input = input_tensor.cpu()

        latencies: list[float] = []
        for _ in range(n_iters):
            if device == "cuda":
                torch.cuda.synchronize()
            start_time = time.perf_counter()
            executor.forward((run_input,))
            if device == "cuda":
                torch.cuda.synchronize()
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the executor and release memory."""
        del handle["executor"]
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed ExecuTorch version string."""
        from importlib.metadata import version as pkg_version
        return pkg_version("executorch")


def _export_and_cache_cuda(pte_path: Path) -> None:
    """Export ResNet50 with CudaPartitioner (AOTInductor-backed) and cache .pte to disk."""
    from torch.export import export as torch_export  # type: ignore[import]
    from executorch.backends.cuda.cuda_backend import CudaBackend  # type: ignore[import]
    from executorch.backends.cuda.cuda_partitioner import CudaPartitioner  # type: ignore[import]
    from executorch.exir import to_edge_transform_and_lower, EdgeCompileConfig  # type: ignore[import]

    # Allow ATEN (cuDNN/cuBLAS) kernels as fallback so convolution has valid choices.
    torch._inductor.config.max_autotune_conv_backends = "ATEN"  # type: ignore[attr-defined]
    torch._inductor.config.max_autotune_gemm_backends = "ATEN"  # type: ignore[attr-defined]

    weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
    model = tv_models.resnet50(weights=weights).eval().cuda()
    dummy_input = torch.zeros(1, 3, 224, 224, dtype=torch.float32, device="cuda")

    exported = torch_export(model, (dummy_input,))
    compile_specs = [CudaBackend.generate_method_name_compile_spec("forward")]
    partitioner = CudaPartitioner(compile_specs)
    edge_program = to_edge_transform_and_lower(
        exported,
        partitioner=[partitioner],
        compile_config=EdgeCompileConfig(_check_ir_validity=False),
    )
    et_program = edge_program.to_executorch()

    pte_path.parent.mkdir(parents=True, exist_ok=True)
    pte_path.write_bytes(et_program.buffer)
    L.info("executorch.cache.saved", path=str(pte_path), device="cuda")


def _export_and_cache_xnnpack(pte_path: Path) -> None:
    """Export ResNet50 with XNNPACK delegate (CPU) and cache .pte to disk."""
    from torch.export import export as torch_export  # type: ignore[import]
    from executorch.exir import to_edge, EdgeCompileConfig  # type: ignore[import]
    from executorch.backends.xnnpack.partition.xnnpack_partitioner import (  # type: ignore[import]
        XnnpackPartitioner,
    )

    weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
    model = tv_models.resnet50(weights=weights).eval()
    dummy_cpu_input = torch.zeros(1, 3, 224, 224, dtype=torch.float32)

    exported = torch_export(model, (dummy_cpu_input,))
    edge = to_edge(exported, compile_config=EdgeCompileConfig(_check_ir_validity=False))
    et_program = edge.to_backend(XnnpackPartitioner()).to_executorch()

    pte_path.parent.mkdir(parents=True, exist_ok=True)
    pte_path.write_bytes(et_program.buffer)
    L.info("executorch.cache.saved", path=str(pte_path), device="cpu")

"""
runtimes/executorch/runtime.py

ExecuTorch runtime adapter: exports ResNet50 via XNNPACK delegate, caches the
compiled program to disk, and runs timed CPU inference.

Note: ExecuTorch's CUDA backend (CudaPartitioner) only supports SDPA/attention
ops, not CNNs. ResNet50 benchmarks run on CPU via XNNPACK.
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
    """Exports ResNet50 with the XNNPACK delegate (CPU) and runs timed inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Export ResNet50 to a .pte file via XNNPACK (cached), load and return executor."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        pte_path = ET_CACHE_DIR / f"{model_name}_{precision}.pte"

        if pte_path.exists():
            L.info("executorch.init.cache_hit", pte_path=str(pte_path))
        else:
            L.info("executorch.init.cache_miss", pte_path=str(pte_path))
            _export_and_cache(pte_path)

        from executorch.extension.pybindings.portable_lib import (  # type: ignore[import]
            _load_for_executorch,
        )

        executor = _load_for_executorch(str(pte_path))
        return executor

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times on CPU with perf_counter timing; return latencies in ms."""
        cpu_input = input_tensor.cpu()
        latencies: list[float] = []
        for _ in range(n_iters):
            start_time = time.perf_counter()
            handle.forward((cpu_input,))
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the executor handle."""
        del handle

    def version(self) -> str:
        """Return the installed ExecuTorch version string."""
        from importlib.metadata import version as pkg_version
        return pkg_version("executorch")


def _export_and_cache(pte_path: Path) -> None:
    """Export ResNet50 with XNNPACK delegate and write the .pte program to pte_path."""
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
    L.info("executorch.cache.saved", path=str(pte_path))

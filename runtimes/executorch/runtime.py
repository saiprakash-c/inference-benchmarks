"""
runtimes/executorch/runtime.py

ExecuTorch runtime adapter: exports the model via XNNPACK delegate, caches the
compiled program to disk, and runs timed CPU inference.

Note: ExecuTorch's CUDA backend (CudaPartitioner) only supports SDPA/attention
ops — not general CNNs. All models run on CPU via XNNPACK.
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import RuntimeBase

ET_CACHE_DIR = Path("/tmp/et_cache")


class ExecuTorchRuntime(RuntimeBase):
    """Exports the model with the XNNPACK delegate (CPU) and runs timed inference."""

    SUPPORTED_PRECISIONS: frozenset[str] = frozenset({"fp32"})

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Export to a .pte file via XNNPACK (cached), load and return executor."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        pte_path = ET_CACHE_DIR / f"{model_name}_{precision}.pte"

        if pte_path.exists():
            L.info("executorch.init.cache_hit", pte_path=str(pte_path))
        else:
            L.info("executorch.init.cache_miss", pte_path=str(pte_path))
            _export_and_cache(model_name, pte_path)

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

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """Run one inference under torch.profiler (CPU activities) and return key_averages table."""
        from torch.profiler import ProfilerActivity
        from torch.profiler import profile as torch_profile

        cpu_input = input_tensor.cpu()
        with torch_profile(activities=[ProfilerActivity.CPU]) as prof:
            handle.forward((cpu_input,))
        return prof.key_averages().table(sort_by="cpu_time_total", row_limit=50)


def _export_and_cache(model_name: str, pte_path: Path) -> None:
    """Export model with XNNPACK delegate and write the .pte program to pte_path."""
    from executorch.backends.xnnpack.partition.xnnpack_partitioner import (  # type: ignore[import]
        XnnpackPartitioner,
    )
    from executorch.exir import EdgeCompileConfig, to_edge  # type: ignore[import]
    from torch.export import export as torch_export  # type: ignore[import]

    model = loader.load(model_name, device="cpu")
    in_shape = loader.input_shape(model_name)
    dummy_cpu_input = torch.zeros(*in_shape, dtype=torch.float32)

    exported = torch_export(model, (dummy_cpu_input,))
    edge = to_edge(exported, compile_config=EdgeCompileConfig(_check_ir_validity=False))
    et_program = edge.to_backend(XnnpackPartitioner()).to_executorch()

    pte_path.parent.mkdir(parents=True, exist_ok=True)
    pte_path.write_bytes(et_program.buffer)
    L.info("executorch.cache.saved", path=str(pte_path))

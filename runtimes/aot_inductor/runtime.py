"""
runtimes/aot_inductor/runtime.py

AOT Inductor runtime adapter: compiles ResNet50 to a .so shared library,
caches it to disk, loads via torch._export.aot_load, and runs timed inference.
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]
import torchvision.models as tv_models  # type: ignore[import]

from lib import log as L
from runtimes.base import RuntimeBase

AOT_CACHE_DIR = Path("/tmp/aot_cache")


class AOTInductorRuntime(RuntimeBase):
    """Compiles ResNet50 via AOT Inductor (.so cached to disk) and runs timed CUDA inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Compile ResNet50 to a .so via AOT Inductor (cached), load and return callable runner."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        cache_path = AOT_CACHE_DIR / f"{model_name}_{precision}_{device}.so"

        if cache_path.exists():
            L.info("aot_inductor.init.cache_hit", so_path=str(cache_path))
            so_path = str(cache_path)
        else:
            L.info("aot_inductor.init.cache_miss", so_path=str(cache_path))
            so_path = _compile_and_cache(cache_path, device)

        runner = torch._export.aot_load(so_path, device)  # type: ignore[attr-defined]
        return runner

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times with CUDA-synchronised timing; return latencies in ms."""
        device_tensor = input_tensor.to("cuda") if not input_tensor.is_cuda else input_tensor
        latencies: list[float] = []
        for _ in range(n_iters):
            torch.cuda.synchronize()
            start_time = time.perf_counter()
            handle(device_tensor)
            torch.cuda.synchronize()
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the runner handle and release CUDA memory."""
        del handle
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed PyTorch version string (AOT Inductor is bundled with PyTorch)."""
        return torch.__version__


def _compile_and_cache(cache_path: Path, device: str) -> str:
    """Compile ResNet50 via AOT Inductor, write the .so to cache_path, return its path string."""
    weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
    model = tv_models.resnet50(weights=weights).eval().to(device)
    dummy_input = torch.zeros(1, 3, 224, 224, dtype=torch.float32, device=device)

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    so_path = torch._inductor.aot_compile(  # type: ignore[attr-defined]
        model,
        (dummy_input,),
        options={"aot_inductor.output_path": str(cache_path)},
    )
    L.info("aot_inductor.cache.saved", path=so_path)
    return so_path

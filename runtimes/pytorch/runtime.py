"""
runtimes/pytorch/runtime.py

PyTorch eager-mode runtime adapter. Loads the requested model via
models.loader and runs timed CUDA inference.
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import PRECISION_TO_DTYPE, RuntimeBase


class PyTorchRuntime(RuntimeBase):
    """Runs inference using PyTorch eager mode with CUDA synchronisation timing."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Load the model, set eval mode, move to device, cast to requested precision."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        L.info("pytorch.init", model=model_name, device=device, precision=precision)
        dtype = PRECISION_TO_DTYPE[precision]
        model = loader.load(model_name, device)
        return model.to(dtype=dtype)

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times with CUDA-synchronised timing; return latencies in ms."""
        param = next(handle.parameters())
        device_tensor = input_tensor.to(device=param.device, dtype=param.dtype)
        latencies: list[float] = []
        with torch.no_grad():
            for _ in range(n_iters):
                torch.cuda.synchronize()
                start_time = time.perf_counter()
                handle(device_tensor)
                torch.cuda.synchronize()
                end_time = time.perf_counter()
                latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the model handle and release CUDA memory."""
        del handle
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed PyTorch version string."""
        return torch.__version__

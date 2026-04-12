"""
runtimes/pytorch/runtime.py

PyTorch eager-mode runtime adapter for ResNet50 inference benchmarking.
"""

import time
from typing import Any

import torch  # type: ignore[import]
import torchvision.models as tv_models  # type: ignore[import]

from runtimes.base import RuntimeBase


class PyTorchRuntime(RuntimeBase):
    """Runs inference using PyTorch eager mode with CUDA synchronisation timing."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Load ResNet50 with IMAGENET1K_V2 weights, set eval mode, move to device."""
        weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
        model = tv_models.resnet50(weights=weights)
        model.eval()
        model.to(device)
        return model

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times with CUDA-synchronised timing; return latencies in ms."""
        device_tensor = input_tensor.to(next(handle.parameters()).device)
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

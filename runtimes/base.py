"""
runtimes/base.py

Runtime interface contract. Every runtime under runtimes/<name>/runtime.py
must subclass RuntimeBase and implement all four methods.

Forward-only: this package imports only from lib/. It does not import
from benchmark/, results/, or site/.

See docs/RUNTIMES.md for the full pluggability contract.
"""

from abc import ABC, abstractmethod
from typing import Any

import torch  # type: ignore[import]

PRECISION_TO_DTYPE: dict[str, torch.dtype] = {
    "fp32": torch.float32,
    "fp16": torch.float16,
}


class RuntimeBase(ABC):

    SUPPORTED_PRECISIONS: frozenset[str] = frozenset({"fp32", "fp16"})

    @abstractmethod
    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Load the model and allocate runtime resources. Returns an opaque handle."""

    @abstractmethod
    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """
        Run inference n_iters times. Returns per-iteration latency in ms.
        Caller has already discarded warmup iterations before calling this.
        """

    @abstractmethod
    def teardown(self, handle: Any) -> None:
        """Release all resources acquired in init()."""

    @abstractmethod
    def version(self) -> str:
        """Return the installed runtime version string."""

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """
        Run a single-inference profiling pass and return a human-readable
        layer-by-layer text report, or None if profiling is not supported.

        Default implementation returns None. Runtimes that support profiling
        should override this method. Called after measurement so p50/p99 are
        unaffected.
        """
        return None

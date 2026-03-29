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


class RuntimeBase(ABC):

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

"""
ExecuTorch runtime adapter.

Stub — implementation pending architecture decisions.
See AGENT_LOOP.md.
"""

from typing import Any

from runtimes.base import RuntimeBase


class ExecuTorchRuntime(RuntimeBase):
    def init(self, model_path: str, precision: str, device: str) -> Any:
        raise NotImplementedError

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        raise NotImplementedError

    def teardown(self, handle: Any) -> None:
        raise NotImplementedError

    def version(self) -> str:
        import executorch  # type: ignore[import]
        return executorch.__version__

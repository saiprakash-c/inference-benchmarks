"""
//benchmark:run

Entry point for the benchmark suite.
Loads each runtime, warms up, measures latency/throughput, writes results/.

Not yet implemented — scaffold only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402


def main() -> int:
    L.info("benchmark.run", status="not_implemented")
    L.error(
        "benchmark.run",
        message="//benchmark:run is not yet implemented. "
        "See docs/features/todo/ for the implementation plan.",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

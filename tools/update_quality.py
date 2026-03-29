"""
//tools:update_quality

Recomputes QUALITY_SCORE.md from current results and doc state.
Not yet implemented — scaffold only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402


def main() -> int:
    L.info("update_quality.run", status="not_implemented")
    L.error(
        "update_quality.run",
        message="//tools:update_quality is not yet implemented.",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

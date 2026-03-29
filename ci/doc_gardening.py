"""
//ci:doc_gardening

Weekly agent job: scan for doc/code drift, update QUALITY_SCORE.md, open fix PRs.
Not yet implemented — scaffold only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402


def main() -> int:
    L.info("doc_gardening.run", status="not_implemented")
    L.error(
        "doc_gardening.run",
        message="//ci:doc_gardening is not yet implemented.",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

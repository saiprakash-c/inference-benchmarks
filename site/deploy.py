"""
//site:deploy

Pushes site/public/ to the gh-pages branch via git subtree.
Must be run after //site:build.

Usage:
  bazel run //site:build && bazel run //site:deploy
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
PUBLIC_DIR = REPO_ROOT / "site" / "public"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    L.info("site.deploy", command=" ".join(cmd))
    return subprocess.run(cmd, cwd=str(REPO_ROOT), **kwargs)


def main() -> int:
    if not PUBLIC_DIR.exists():
        L.error("site.deploy", reason="site/public/ does not exist — run //site:build first")
        return 2

    # Ensure we have a clean working tree for the subtree push
    status = _run(["git", "status", "--porcelain", "site/public/"], capture_output=True, text=True)
    if status.stdout.strip():
        # Stage the built site
        _run(["git", "add", "site/public/"])

    # Push site/public/ as the root of the gh-pages branch
    result = _run([
        "git", "subtree", "push",
        "--prefix", "site/public",
        "origin", "gh-pages",
    ])

    if result.returncode != 0:
        L.error("site.deploy", returncode=result.returncode, reason="git subtree push failed")
        return 1

    L.info("site.deploy", status="ok", branch="gh-pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())

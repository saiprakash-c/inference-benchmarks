"""
//site:deploy

Pushes site/public/ to the gh-pages branch via a clean orphan commit.
Must be run after //site:build.

Usage:
  bazel run //site:build && bazel run //site:deploy
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
PUBLIC_DIR = REPO_ROOT / "site" / "public"


def _run(cmd: list[str], cwd: str, **kwargs) -> subprocess.CompletedProcess:
    L.info("site.deploy", command=" ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, **kwargs)


def main() -> int:
    if not PUBLIC_DIR.exists():
        L.error("site.deploy", reason="site/public/ does not exist — run //site:build first")
        return 2

    # Get the remote URL so we can push from a temp worktree
    remote_result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if remote_result.returncode != 0:
        L.error("site.deploy", reason="could not get origin remote URL")
        return 1
    remote_url = remote_result.stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        # Init a fresh repo and create an orphan gh-pages branch
        _run(["git", "init"], cwd=tmp)
        _run(["git", "checkout", "--orphan", "gh-pages"], cwd=tmp)
        _run(["git", "config", "user.name", "github-actions[bot]"], cwd=tmp)
        _run(["git", "config", "user.email",
              "github-actions[bot]@users.noreply.github.com"], cwd=tmp)

        # Copy build output into the temp repo
        for src in PUBLIC_DIR.rglob("*"):
            if src.is_file():
                rel = src.relative_to(PUBLIC_DIR)
                dest = Path(tmp) / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))

        _run(["git", "add", "."], cwd=tmp)
        _run(["git", "commit", "-m", "deploy: update gh-pages"], cwd=tmp)

        result = _run(
            ["git", "push", "--force", remote_url, "HEAD:gh-pages"],
            cwd=tmp,
        )
        if result.returncode != 0:
            L.error("site.deploy", returncode=result.returncode, reason="push to gh-pages failed")
            return 1

    L.info("site.deploy", status="ok", branch="gh-pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())

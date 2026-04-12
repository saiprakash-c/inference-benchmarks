"""
//site:deploy

Pushes site/public/ to the gh-pages branch using a persistent local clone.
Must be run after //site:build.

Usage:
  bazel run //site:build && bazel run //site:deploy

The clone at GH_PAGES_CLONE_DIR is created on first run and reused on
subsequent runs. Authentication uses `gh auth git-credential` — no SSH
keys or embedded tokens required.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
PUBLIC_DIR = REPO_ROOT / "site" / "public"
GH_PAGES_CLONE_DIR = Path("/tmp/gh-pages-deploy")

_GIT_CREDENTIAL_HELPER = ["git", "-c", "credential.helper=!gh auth git-credential"]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    L.info("site.deploy", command=" ".join(cmd))
    return subprocess.run(cmd, **kwargs)


def _get_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("could not get origin remote URL")
    url = result.stdout.strip()
    # Strip any embedded credentials — gh auth git-credential handles auth
    if url.startswith("https://") and "@" in url:
        url = "https://" + url.split("@", 1)[1]
    return url


def _ensure_clone(remote_url: str) -> None:
    """Create the persistent clone if it does not exist."""
    if GH_PAGES_CLONE_DIR.exists():
        return
    L.info("site.deploy.clone", path=str(GH_PAGES_CLONE_DIR))
    result = _run(
        _GIT_CREDENTIAL_HELPER + [
            "clone", "--branch", "gh-pages", "--depth", "1",
            remote_url, str(GH_PAGES_CLONE_DIR),
        ],
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to clone gh-pages to {GH_PAGES_CLONE_DIR}")


def main() -> int:
    if not PUBLIC_DIR.exists():
        L.error("site.deploy", reason="site/public/ does not exist — run //site:build first")
        return 2

    try:
        remote_url = _get_remote_url()
        _ensure_clone(remote_url)
    except RuntimeError as exc:
        L.error("site.deploy", reason=str(exc))
        return 1

    clone = str(GH_PAGES_CLONE_DIR)

    # Pull latest so we build on top of any changes pushed by other means
    _run(
        _GIT_CREDENTIAL_HELPER + ["pull"],
        cwd=clone,
    )

    # Sync public/ into the clone (delete stale files, copy new ones)
    for f in GH_PAGES_CLONE_DIR.iterdir():
        if f.name == ".git":
            continue
        if f.is_dir():
            shutil.rmtree(str(f))
        else:
            f.unlink()

    for src in PUBLIC_DIR.rglob("*"):
        if src.is_file():
            rel = src.relative_to(PUBLIC_DIR)
            dest = GH_PAGES_CLONE_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))

    # Check for changes before committing
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=clone, capture_output=True, text=True,
    )
    if not status.stdout.strip():
        L.info("site.deploy", status="no-op", reason="gh-pages already up to date")
        return 0

    _run(["git", "add", "-A"], cwd=clone)
    _run(["git", "commit", "-m", "deploy: update gh-pages"], cwd=clone)

    result = _run(
        _GIT_CREDENTIAL_HELPER + ["push", "origin", "gh-pages"],
        cwd=clone,
    )
    if result.returncode != 0:
        L.error("site.deploy", returncode=result.returncode, reason="push to gh-pages failed")
        return 1

    L.info("site.deploy", status="ok", branch="gh-pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())

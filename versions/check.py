"""
//versions:check

Reads versions.toml, queries installed runtime versions inside the container,
diffs against the recorded state, and writes an update if anything changed.

Exit codes:
  0  — versions unchanged; no benchmark run needed
  1  — versions changed; caller should trigger //benchmark:run
  2  — fatal error (unreadable file, unexpected exception)
"""

import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import tomli_w

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.toml"


# ── Version queriers ───────────────────────────────────────────────────────────


def _query_pytorch() -> str | None:
    try:
        import torch  # type: ignore[import]
        return torch.__version__
    except ImportError:
        return None


def _query_tensorrt() -> str | None:
    try:
        import tensorrt  # type: ignore[import]
        return tensorrt.__version__
    except ImportError:
        return None


def _query_executorch() -> str | None:
    try:
        import executorch  # type: ignore[import]
        return executorch.__version__
    except ImportError:
        return None


def _query_cuda() -> str | None:
    try:
        import torch  # type: ignore[import]
        return torch.version.cuda
    except Exception:
        pass
    # Fallback: parse nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def _query_jetpack() -> str | None:
    # Check environment variable first (set in Dockerfile for reproducibility)
    import os
    if (ver := os.environ.get("JETPACK_VERSION")):
        return ver
    # Fallback: dpkg on Jetson devices
    try:
        result = subprocess.run(
            ["dpkg-query", "--showformat=${Version}", "--show", "nvidia-jetpack"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


QUERIERS: dict[str, object] = {
    "pytorch": _query_pytorch,
    "tensorrt": _query_tensorrt,
    "executorch": _query_executorch,
    "cuda": _query_cuda,
    "jetpack": _query_jetpack,
}


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    try:
        with open(VERSIONS_FILE, "rb") as f:
            current = tomllib.load(f)
    except Exception as exc:
        L.error("versions.check", error=str(exc), file=str(VERSIONS_FILE))
        return 2

    now = datetime.now(timezone.utc).isoformat()

    # Query installed versions
    installed: dict[str, str] = {}
    for name, querier in QUERIERS.items():
        version = querier()  # type: ignore[operator]
        if version is None:
            L.warn("versions.check", runtime=name, status="not_found")
        else:
            installed[name] = version

    L.info("versions.check", installed=installed)

    # Diff against versions.toml [runtimes]
    recorded = current.get("runtimes", {})
    changed = [
        {"runtime": name, "old": recorded.get(name), "new": ver}
        for name, ver in installed.items()
        if recorded.get(name) != ver
    ]

    # Build updated document
    updated = {**current}
    updated["meta"] = {**current.get("meta", {}), "last_checked": now}
    updated["runtimes"] = {**recorded, **installed}

    try:
        with open(VERSIONS_FILE, "wb") as f:
            tomli_w.dump(updated, f)
    except Exception as exc:
        L.error("versions.check", error=str(exc), file=str(VERSIONS_FILE))
        return 2

    if changed:
        L.info("versions.check", status="changed", changed=changed)
        return 1

    L.info("versions.check", status="unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
hardware/thor.py

Thor hardware identification and GPU introspection.
Used by benchmark/runner.py to populate hw_id in result JSON.

Forward-only: this package imports only from lib/. It does not import
from inputs/, models/, runtimes/, benchmark/, results/, or site/.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

HW_ID = "thor"


def hw_id() -> str:
    """Return the canonical hardware identifier for this machine."""
    return HW_ID


def gpu_info() -> dict:
    """
    Return basic GPU info from nvidia-smi.
    Returns an empty dict if nvidia-smi is unavailable (e.g. during CI lint).
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) >= 3:
            return {"gpu_name": parts[0], "memory_mb": parts[1], "driver": parts[2]}
    except Exception as exc:
        L.warn("hardware.thor", reason=f"nvidia-smi failed: {exc}")
    return {}

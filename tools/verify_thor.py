"""
//tools:verify_thor

Verifies Thor is benchmark-ready. Runs from Mac over SSH via Tailscale.
Checks: SSH reachable, Docker + GPU accessible, JETPACK_VERSION set, GHCR login.

Exit codes:
  0 — all checks passed
  1 — one or more checks failed
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

THOR_HOST = "saip@thor"
GHCR_IMAGE = "ghcr.io/saiprakash-c/inference-benchmarks:latest"


def run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check(name: str, passed: bool, detail: str = "") -> bool:
    if passed:
        L.info("verify_thor.pass", check=name, detail=detail)
    else:
        L.error("verify_thor.fail", check=name, detail=detail)
    return passed


def main() -> int:
    results = []

    # ── Check 1: SSH reachable ─────────────────────────────────────────────────
    rc, out, _ = run(["ssh", "-o", "ConnectTimeout=10", THOR_HOST, "echo ok"])
    results.append(check("ssh", rc == 0 and out == "ok", "ssh saip@thor"))

    if rc != 0:
        L.error("verify_thor.abort", reason="Cannot reach Thor over SSH — aborting remaining checks")
        return 1

    # ── Check 2: Docker daemon running ────────────────────────────────────────
    rc, out, _ = run(["ssh", THOR_HOST, "docker info --format '{{.ServerVersion}}' 2>/dev/null"])
    results.append(check("docker", rc == 0 and out, f"version={out}"))

    # ── Check 3: nvidia default runtime ──────────────────────────────────────
    rc, out, _ = run(["ssh", THOR_HOST,
        "docker info --format '{{.DefaultRuntime}}' 2>/dev/null"])
    results.append(check("nvidia_runtime", out == "nvidia", f"default_runtime={out!r}"))

    # ── Check 4: GPU accessible in container ─────────────────────────────────
    rc, out, _ = run(["ssh", THOR_HOST,
        "docker run --rm --gpus all ubuntu:22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null"],
        timeout=60)
    results.append(check("gpu_in_container", rc == 0 and out, f"gpu={out!r}"))

    # ── Check 5: JETPACK_VERSION set ─────────────────────────────────────────
    rc, out, _ = run(["ssh", THOR_HOST, "grep JETPACK_VERSION /etc/environment"])
    results.append(check("jetpack_version", rc == 0 and "JETPACK_VERSION" in out, out))

    # ── Check 6: GHCR pull (public image, no auth needed) ────────────────────
    rc, out, _ = run(["ssh", THOR_HOST,
        f"docker pull {GHCR_IMAGE} 2>&1 | tail -1"], timeout=120)
    ghcr_ok = rc == 0 or "Status: Image is up to date" in out or "Downloaded newer image" in out
    results.append(check("ghcr_pull", ghcr_ok,
        "skipped — image not yet pushed to GHCR" if not ghcr_ok else out))

# ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(results)
    total = len(results)
    if all(results):
        L.info("verify_thor.summary", status="pass", passed=passed, total=total)
        return 0
    else:
        L.error("verify_thor.summary", status="fail", passed=passed, total=total)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
//tools:ssh_run

Discovers Thor on Tailscale, SSHs in, and executes a Bazel target inside
the Docker container. All //benchmark:run invocations must go through this
tool — running benchmark targets locally is a lint error.

Usage:
  bazel run //tools:ssh_run -- //benchmark:run
  bazel run //tools:ssh_run -- //versions:check

Required:
  Tailscale must be running and Thor must be online in the tailnet.
  THOR_SSH_KEY — path to the SSH private key file for Thor.

Thor is discovered automatically via `tailscale status --json` by looking
for a peer whose hostname contains "thor" (case-insensitive).
"""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.toml"
THOR_HOSTNAME_FRAGMENT = "thor"
IMAGE_NAME = "ghcr.io/saiprakash-c/inference-benchmarks"


# ── Tailscale discovery ────────────────────────────────────────────────────────


def _discover_thor() -> str:
    """Return Thor's Tailscale IP by searching tailscale status peers."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        L.error("ssh_run.error", reason="tailscale CLI not found — is Tailscale installed and running?")
        sys.exit(2)

    if result.returncode != 0:
        L.error("ssh_run.error", reason=f"tailscale status failed: {result.stderr.strip()}")
        sys.exit(2)

    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        L.error("ssh_run.error", reason=f"could not parse tailscale status: {exc}")
        sys.exit(2)

    for peer in status.get("Peer", {}).values():
        hostname = peer.get("HostName", "").lower()
        online = peer.get("Online", False)
        if THOR_HOSTNAME_FRAGMENT in hostname:
            if not online:
                L.error(
                    "ssh_run.error",
                    reason=f"Thor ({hostname}) found in tailscale but is offline",
                )
                sys.exit(2)
            ips = peer.get("TailscaleIPs", [])
            if ips:
                L.info("ssh_run.thor_found", hostname=hostname, ip=ips[0])
                return ips[0]

    available = [
        f"{p.get('HostName', '?')} (online={p.get('Online', False)})"
        for p in status.get("Peer", {}).values()
    ]
    L.error(
        "ssh_run.error",
        reason=(
            f"Thor not found in tailscale status "
            f"(searching for hostname containing '{THOR_HOSTNAME_FRAGMENT}')"
        ),
        available_peers=available,
    )
    sys.exit(2)


# ── Digest verification ────────────────────────────────────────────────────────


def _verify_digest(host: str, key: str, expected_digest: str) -> bool:
    """Confirm the image on Thor matches versions.toml [docker].digest."""
    check_cmd = (
        f"docker image inspect --format='{{{{index .RepoDigests 0}}}}' "
        f"'{IMAGE_NAME}' 2>/dev/null || true"
    )
    result = subprocess.run(
        ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no", host, check_cmd],
        capture_output=True, text=True, timeout=30,
    )
    observed = result.stdout.strip().strip("'")
    if expected_digest not in observed:
        L.error(
            "docker.digest_mismatch",
            expected=expected_digest,
            observed=observed or "(image not found)",
            reason=(
                "Image digest on Thor does not match versions.toml [docker].digest. "
                "Run `docker pull` on Thor or rebuild the image. Escalate if unclear."
            ),
        )
        return False
    return True


# ── Main ───────────────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        L.error("ssh_run.error", reason="usage: ssh_run <//bazel:target> [args...]")
        return 2

    target = argv[1]
    extra_args = argv[2:]

    key = os.environ.get("THOR_SSH_KEY")
    if not key:
        L.error("ssh_run.error", reason="THOR_SSH_KEY env var not set (path to SSH private key)")
        return 2

    with open(VERSIONS_FILE, "rb") as f:
        versions = tomllib.load(f)

    expected_digest = versions.get("docker", {}).get("digest", "")
    if not expected_digest or expected_digest.startswith("sha256:abc"):
        L.error("ssh_run.error", reason="[docker].digest not set in versions.toml — build and push the image first")
        return 2

    host = _discover_thor()
    L.info("ssh_run.start", target=target, host=host, digest=expected_digest)

    if not _verify_digest(host, key, expected_digest):
        return 2

    # Run the Bazel target inside the container on Thor
    bazel_cmd = " ".join(["bazel", "run", target] + extra_args)
    docker_cmd = (
        f"docker run --rm --gpus all "
        f"--volume /workspace:/workspace "
        f"'{IMAGE_NAME}@{expected_digest}' "
        f"{bazel_cmd}"
    )
    ssh_cmd = ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no", host, docker_cmd]

    L.info("ssh_run.exec", host=host, target=target)
    result = subprocess.run(ssh_cmd)

    if result.returncode != 0:
        L.error("ssh_run.done", target=target, returncode=result.returncode)
    else:
        L.info("ssh_run.done", target=target, returncode=0)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))

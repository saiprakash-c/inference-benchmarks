# Summary: thor-provisioning
Completed: 2026-04-05

## What was built

- `docker/Dockerfile` — refactored to `pip install .[gpu]` from pyproject.toml
- `docker/Dockerfile.dev` — new lightweight dev image (`python:3.12-slim`, CPU-only, Mac/CI)
- `docker/docker-compose.yml` — `dev` and `runtime` services, one command to launch either
- `pyproject.toml` — added `[project.optional-dependencies]` with `dev` and `gpu` extras; all dep versions now in one place
- `docs/THOR_SETUP.md` — full runbook: factory boot → Tailscale → SSH → Docker → GHCR → verify
- `tools/verify_thor.py` — 6-check script: SSH, Docker, nvidia runtime, GPU in container, JETPACK_VERSION, GHCR pull
- `tools/ssh_run.py` — falls back to `saip@thor` (system SSH config) when `THOR_SSH_KEY` not set
- Thor configured: nvidia default runtime, saip in docker group, passwordless sudo, `JETPACK_VERSION=38.4.0`

## Deviations from plan

- Used `gpu` extra instead of `jetson` — same packages, cleaner name (works for any GPU target)
- GHCR login left as manual step (requires GitHub PAT; cannot be scripted without secrets)
- `JETPACK_VERSION` set to `38.4.0` (L4T revision) rather than `6.4` — Thor runs L4T r38, not JetPack 6.x

## Lessons learned

- JetPack base images (`l4t-*`) are obsolete for JetPack 6+; community (jetson-containers) uses `ubuntu:22.04` + NVIDIA apt repos. For JetPack 7 (r38), use `ubuntu:24.04`.
- Multi-stage Dockerfiles don't help here — Jetson and x86/Mac wheels are incompatible binaries; two separate Dockerfiles sharing `pyproject.toml` is the right pattern.
- Jetson PyTorch wheels come from `pypi.jetson-ai-lab.io`, not PyPI.

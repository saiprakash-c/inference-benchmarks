# Summary: thor-provisioning
Completed: 2026-04-05

## What was built

- `docker/Dockerfile` — runtime image: `cuda:13.0.2-runtime-ubuntu24.04` base, TensorRT via apt, `pip install .[gpu]`
- `docker/Dockerfile.dev` — new lightweight dev image (`python:3.12-slim`, CPU-only, Mac/CI)
- `docker/docker-compose.yml` — `dev` and `runtime` services, one command to launch either
- `bin/docker_dev` — convenience script to enter the dev container
- `bin/docker_rt` — convenience script to enter the runtime container on Thor (GPU)
- `pyproject.toml` — added `[project.optional-dependencies]` with `dev` and `gpu` extras; all dep versions now in one place
- `docs/THOR_SETUP.md` — full runbook: factory boot → Tailscale → SSH → Docker → GHCR → verify
- `tools/verify_thor.py` — 6-check script: SSH, Docker, nvidia runtime, GPU in container, JETPACK_VERSION, GHCR pull
- `tools/ssh_run.py` — falls back to `saip@thor` (system SSH config) when `THOR_SSH_KEY` not set
- Thor configured: nvidia default runtime, saip in docker group, passwordless sudo, `JETPACK_VERSION=38.4.0`

## Deviations from plan

- Used `gpu` extra instead of `jetson` — same packages, cleaner name (works for any GPU target)
- Runtime Dockerfile base changed from `l4t-tensorrt` to `nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04` — no official `l4t-*` image exists for JetPack 7 (L4T R38); TensorRT 10.16.0 installed via NVIDIA Jetson apt repo (r38.4)
- GHCR login is n/a — repo is public, no PAT needed to pull the image
- `JETPACK_VERSION` set to `38.4.0` (L4T revision) rather than `6.4` — Thor runs L4T r38, not JetPack 6.x

## Lessons learned

- JetPack base images (`l4t-*`) are obsolete for JetPack 7 (L4T R38) — no official image exists yet. Use `nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04` and install TensorRT via the NVIDIA Jetson apt repo (`r38.4`).
- Multi-stage Dockerfiles don't help here — Jetson and x86/Mac wheels are incompatible binaries; two separate Dockerfiles sharing `pyproject.toml` is the right pattern.
- Jetson PyTorch wheels come from `pypi.jetson-ai-lab.io`, not PyPI.

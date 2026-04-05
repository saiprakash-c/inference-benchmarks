# Plan: thor-provisioning
Status: completed

---

## Requirements from User

- Provision Thor with JetPack, Docker, and everything needed to run benchmarks
- Clear documentation so a new Thor can be provisioned from scratch
- Document the YouTube-guided boot steps + Tailscale install that were done initially

---

## Updates on User Requirements

**JetPack is already installed** (R38.4.0 / CUDA 13.0). The plan documents what was done rather than re-doing it.

**Added:** `tools/verify_thor.py` — a script that confirms Thor is benchmark-ready in one command. Not in requirements but essential for reproducibility.

**Added:** `THOR_SSH_KEY` handling in `tools/ssh_run.py` — for local dev, fall back to system SSH config (`saip@thor`) when `THOR_SSH_KEY` is not set. CI still uses the explicit key.

---

## Design

### Thor provisioning layers

```
┌─────────────────────────────────────────────────┐
│  Benchmark layer                                │
│  GHCR image pull · JETPACK_VERSION env var      │
├─────────────────────────────────────────────────┤
│  Container layer                                │
│  Docker 28 · nvidia-container-runtime (default) │
│  saip in docker group · passwordless sudo       │
├─────────────────────────────────────────────────┤
│  Network layer                                  │
│  Tailscale (100.117.216.89) · SSH key auth      │
├─────────────────────────────────────────────────┤
│  OS / hardware layer                            │
│  Ubuntu 24.04 · JetPack R38.4.0 · CUDA 13.0    │
│  NVIDIA Thor GPU · 937 GB NVMe                  │
└─────────────────────────────────────────────────┘
```

### Docker image strategy

```
docker/
  Dockerfile              ← Thor: cuda:13.0.2-runtime-ubuntu24.04 base, pip install .[gpu]
  Dockerfile.dev          ← Mac:  python:3.12-slim,  pip install .[dev]
  docker-compose.yml      ← unified entry point for both

pyproject.toml            ← single source of truth for all deps + extras
  [project.dependencies]      core deps (always installed)
  [project.optional-dependencies]
    dev = CPU/Mac extras
    gpu = Jetson CUDA wheel index + GPU packages
```

```
              ┌──── pyproject.toml ────┐
              │  [dependencies]        │
              │  [extras: dev]         │
              │  [extras: gpu]         │
              └──────────┬────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    Dockerfile.dev                 Dockerfile
  pip install .[dev]           pip install .[gpu]
  python:3.12-slim             cuda:13.0.2-ubuntu24.04 base
  Mac · CI · dev               Thor · GPU · prod
```

**One command to launch either:**
```bash
docker compose run dev     bazel run //ci:lint        # Mac
docker compose run runtime bazel run //benchmark:run  # Thor
```

- Both Dockerfiles are ~10 lines — base image + `pip install .[extra]`
- All dep versions and extras live in `pyproject.toml` only
- `runtime` service requires `runtime: nvidia` — only works on Thor

### Current state vs target

| Item | State |
|---|---|
| JetPack R38.4.0 | ✅ done |
| Docker + nvidia-container-runtime | ✅ done |
| saip in docker group | ✅ done |
| Passwordless sudo | ✅ done |
| SSH key auth | ✅ done |
| Tailscale | ✅ done |
| `JETPACK_VERSION` env var | ✅ done (38.4.0) |
| GHCR login on Thor | n/a — repo is public, no auth needed |
| `docs/THOR_SETUP.md` runbook | ✅ done |
| `tools/verify_thor.py` | ✅ done |
| `ssh_run.py` local fallback | ✅ done |

### ssh_run.py local vs CI mode

```
Local dev                          CI (GitHub Actions)
──────────────────                 ──────────────────────
THOR_SSH_KEY not set               THOR_SSH_KEY = secret key path
     │                                      │
     ▼                                      ▼
ssh saip@thor (system config)      ssh -i $THOR_SSH_KEY <ip>
```

---

## Tasks

- [x] Update `pyproject.toml` — add `[project.optional-dependencies]` with `dev` and `gpu` extras
- [x] Refactor `docker/Dockerfile` — `cuda:13.0.2-runtime-ubuntu24.04` base + TensorRT via apt + `pip install .[gpu]`
- [x] Write `docker/Dockerfile.dev` — minimal: `python:3.12-slim` base + `pip install .[dev]`
- [x] Write `docker/docker-compose.yml` — `dev` and `runtime` services
- [x] Set `JETPACK_VERSION=38.4.0` in `/etc/environment` on Thor
- [x] Configure GHCR login on Thor — n/a, repo is public; no PAT needed to pull `ghcr.io` image
- [x] Write `docs/THOR_SETUP.md` — full runbook from factory flash to benchmark-ready
- [x] Write `tools/verify_thor.py` — check SSH, Docker+GPU, GHCR pull, env vars
- [x] Update `tools/ssh_run.py` — fall back to `saip@thor` when `THOR_SSH_KEY` unset

---

## Updates on Approved Plan

_(append here after approval — do not modify above)_

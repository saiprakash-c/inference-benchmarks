# Docker Design

Two images, no Python packages installed — all deps managed by Bazel.

---

## Design goals

| Goal | How it's achieved |
|---|---|
| **Reproducible benchmarks** | All GPU workloads run inside a pinned container; host GPU driver is the only variable |
| **Works on Mac, CI, and Thor** | Two separate images; `dev` runs anywhere x86/arm64 CPU, `runtime` runs on Thor with the nvidia runtime |
| **No root files on the host** | Container user matches host `$UID`/`$USER` — files written inside `/workspace` are owned by you on the host |
| **Persistent identity** | `~/.claude`, `~/.config/gh`, `~/.zsh_history` are bind-mounted — sessions, auth, and history survive container restarts |
| **One command to enter** | `bin/docker_dev` / `bin/docker_rt` handle pre-flight, build, and launch |
| **Bazel owns all Python deps** | `requirements.in` / `requirements.txt` are the single source of truth; no pip installs in Docker |

---

## Two-image split

```
                      requirements.in / requirements.txt
                        (Bazel pip hub — all Python deps)
                                      │
                   ┌──────────────────┴──────────────────┐
                   │                                      │
                   ▼                                      ▼
      ┌────────────────────┐                ┌────────────────────┐
      │   Dockerfile.dev   │                │     Dockerfile     │
      │                    │                │                    │
      │ python:3.12-slim   │                │ cuda:13.0.2-       │
      │ + Bazel + gh CLI   │                │ ubuntu24.04        │
      │ + Node + Claude    │                │ + TensorRT 10.16.0 │
      │                    │                │ + Bazel + gh CLI   │
      │ CPU only           │                │ + Node + Claude    │
      │ Mac · CI · dev     │                │ Thor only · GPU    │
      └────────┬───────────┘                └────────┬───────────┘
               │                                     │
               ▼                                     ▼
        docker compose                         docker compose
        run dev                                run runtime
        bin/docker_dev                         bin/docker_rt
```

**Why two Dockerfiles instead of one multi-stage?**
Jetson GPU wheels (`pypi.jetson-ai-lab.io`) and Mac/x86 wheels are
incompatible binaries — there is no shared stage. Two thin Dockerfiles
are simpler and more explicit than a multi-stage file with platform
conditionals.

**Why Bazel for Python deps instead of Docker pip installs?**
`requirements.txt` is the single source of truth for all Python
dependencies, including Jetson-specific wheels (torch, torch-tensorrt,
executorch) via the Jetson extra index. This means deps are versioned,
reproducible, and declared per-target in BUILD files — not baked
opaquely into the image.

---

## Runtime image base

```
nvcr.io/nvidia/cuda:13.0.2-devel-ubuntu24.04   (arm64)
         │
         │  apt install tensorrt          ← NVIDIA Jetson repo r38.4
         │  install Bazel, gh, Node, Claude Code
         │  ENV TRITON_PTXAS_PATH=...     ← point triton at CUDA 13.0 ptxas
         │
         ▼
ghcr.io/saiprakash-c/inference-benchmarks:latest
```

No official `l4t-*` image exists for JetPack 7 (L4T R38). The CUDA base
image is NVIDIA-published, multi-arch, and keeps TensorRT decoupled from
the base so the version is explicit and auditable in `versions.toml`.

---

## Volume mounts

Both services mount the same set of paths:

```
Host                          Container
──────────────────────────    ─────────────────────────────
~/inference-benchmarks/    →  /workspace          (read-write, repo)
~/.ssh/                    →  ~/.ssh/             (read-only,  git/SSH auth)
~/.gitconfig               →  ~/.gitconfig        (read-write, gh auth setup)
~/.config/gh/              →  ~/.config/gh/       (read-write, gh CLI token)
~/.claude/                 →  ~/.claude/          (read-write, Claude sessions)
~/.claude.json             →  ~/.claude.json      (read-write, Claude config)
~/.zsh_history             →  ~/.zsh_history      (read-write, shell history)
```

---

## User identity

```
docker compose build
       │
       │  --build-arg USERNAME=$USER   ← your shell username
       │  --build-arg UID=$UID         ← your shell UID
       │
       ▼
RUN userdel -r ubuntu   # remove base-image UID 1000 placeholder
RUN useradd -m -u $UID -s /bin/zsh $USERNAME
USER $USERNAME
```

Files written inside `/workspace` are owned by `$UID` on the host — no
`sudo chown` needed after container exits.

---

## How to enter a container

```
bin/docker_dev              bin/docker_rt
      │                           │
      │  touch/mkdir prereqs      │  touch/mkdir prereqs
      │                           │
      │  docker compose run       │  docker compose run
      │    --rm --build           │    --rm
      │    --entrypoint zsh       │    --entrypoint zsh
      │    dev                    │    runtime
      │                           │
      ▼                           ▼
  zsh inside dev             zsh inside runtime
  /workspace mounted         /workspace mounted
  CPU only                   GPU visible (nvidia-smi works)
```

Or directly via compose for non-interactive use:

```bash
docker compose -f docker/docker-compose.yml run --rm dev     bazel run //ci:lint
docker compose -f docker/docker-compose.yml run --rm runtime bazel run //benchmark:run
```

---

## Build and push lifecycle

```
Edit Dockerfile or requirements.in
           │
           ▼
  bazel run //docker:build        ← builds ghcr.io/…:latest locally
           │
           ▼
  bazel run //docker:push         ← pushes to GHCR
           │
           ▼
  update versions.toml            ← set [docker].digest to new digest
           │
           ▼
  commit versions.toml            ← pinned digest is the source of truth
```

The `dev` image is never pushed — it is always built locally from source.
Only the `runtime` image is published to GHCR and digest-pinned.

---

## Key files

| File | Purpose |
|---|---|
| `docker/Dockerfile` | Runtime image (Thor, GPU) |
| `docker/Dockerfile.dev` | Dev image (Mac, CI, CPU) |
| `docker/docker-compose.yml` | Unified entry point for both |
| `docker/saip.zshrc` | zsh prompt + history config, appended to `~/.zshrc` in both images |
| `bin/docker_rt` | Enter runtime container on Thor |
| `bin/docker_dev` | Enter dev container on Mac/CI/any CPU host |
| `versions.toml [docker]` | Pinned digest + CUDA/JetPack versions |
| `requirements.in` | All Python dep declarations (source of truth) |
| `requirements.txt` | Locked deps generated by pip-compile |

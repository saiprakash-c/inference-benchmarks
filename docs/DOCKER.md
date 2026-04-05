# Docker Design

Two images, one `pyproject.toml`, one entry point per environment.

---

## Design goals

| Goal | How it's achieved |
|---|---|
| **Reproducible benchmarks** | All GPU workloads run inside a pinned container; host GPU driver is the only variable |
| **Works on Mac and Thor** | Two separate images share `pyproject.toml`; no multi-stage hacks or platform conditionals in Python deps |
| **No root files on the host** | Container user matches host `$UID`/`$USER` — files written inside `/workspace` are owned by you on the host |
| **Persistent identity** | `~/.claude`, `~/.config/gh`, `~/.zsh_history` are bind-mounted — sessions, auth, and history survive container restarts |
| **One command to enter** | `bin/docker_dev` / `bin/docker_rt` handle pre-flight, build, and launch |

---

## Two-image split

```
┌─────────────────────────────────────────────────────────────────┐
│                        pyproject.toml                           │
│                                                                 │
│   [dependencies]       core (always)                            │
│   [extras.dev]         linting, testing, CI tooling             │
│   [extras.gpu]         TensorRT, PyTorch Jetson wheels          │
└──────────────────────┬──────────────────────┬───────────────────┘
                       │                      │
           pip install .[dev]      pip install .[gpu]
                       │                      │
                       ▼                      ▼
          ┌────────────────────┐   ┌────────────────────┐
          │   Dockerfile.dev   │   │     Dockerfile     │
          │                    │   │                    │
          │ python:3.12-slim   │   │ cuda:13.0.2-       │
          │ + Bazel + gh CLI   │   │ ubuntu24.04        │
          │ + Node + Claude    │   │ + TensorRT 10.16   │
          │                    │   │ + Bazel + gh CLI   │
          │ CPU only           │   │ + Node + Claude    │
          │ Mac · CI · dev     │   │                    │
          └────────┬───────────┘   │ GPU (nvidia rt)    │
                   │               │ Thor only          │
                   │               └────────┬───────────┘
                   │                        │
                   ▼                        ▼
            docker compose              docker compose
            run dev                     run runtime
            bin/docker_dev              bin/docker_rt
```

**Why two Dockerfiles instead of one multi-stage?**
Jetson GPU wheels (`pypi.jetson-ai-lab.io`) and Mac/x86 wheels are
incompatible binaries — there is no shared stage. Keeping two thin
Dockerfiles that both point at `pyproject.toml` is simpler and more
explicit than a multi-stage file with platform conditionals.

---

## Runtime image base

```
nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04   (arm64)
         │
         │  apt install tensorrt          ← NVIDIA Jetson repo r38.4
         │  pip install .[gpu]            ← pypi.jetson-ai-lab.io + PyPI
         │  install Bazel, gh, Node, Claude Code
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

**Why read-write on `.gitconfig`?**
`gh auth setup-git` writes the credential helper into `.gitconfig`. Making
it read-only would prevent the first-time auth setup inside the container.

**Why pre-create the bind-mount files?**
If a host path does not exist when Docker mounts it, Docker creates a
*directory* at that path instead of a file. `bin/docker_dev` and
`bin/docker_rt` both run `touch` / `mkdir -p` on these paths before
launching compose to prevent this.

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
`sudo chown` needed after container exits. The `ubuntu` user in the CUDA
base image is deleted first to avoid a UID collision.

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
# Run a single Bazel target and exit
docker compose -f docker/docker-compose.yml run --rm dev     bazel run //ci:lint
docker compose -f docker/docker-compose.yml run --rm runtime bazel run //benchmark:run
```

---

## Build and push lifecycle

```
Edit Dockerfile or pyproject.toml
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
| `bin/docker_dev` | Enter dev container on Mac/CI |
| `versions.toml [docker]` | Pinned digest + CUDA/JetPack versions |

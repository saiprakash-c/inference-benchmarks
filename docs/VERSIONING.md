# VERSIONING

How versions.toml works and what gets tracked.

## Purpose

versions.toml is the single source of truth for runtime version state and
execution environment. It is committed with every benchmark run. Any result
not accompanied by a committed versions.toml update is incomplete. Git history
of versions.toml is the human-readable changelog — no separate changelog is
maintained.

## Schema

```toml
[meta]
last_checked     = "2026-03-28T00:00:00Z"   # ISO 8601, UTC — when //versions:check last ran
last_benchmarked = "2026-03-27T00:00:00Z"   # ISO 8601, UTC — when last valid result produced

[runtimes]
tensorrt       = "10.16.0.72"
torch_tensorrt = "2.11.0"
pytorch        = "2.11.0"
executorch     = "1.2.0"
aot_inductor   = "2.11.0"
cuda           = "13.0"
jetpack        = "38.4.0"

[docker]
image   = "ghcr.io/saiprakash-c/inference-benchmarks:latest"
digest  = "sha256:abc123..."   # full digest — never just a tag
cuda    = "13.0"
jetpack = "38.4.0"

[sources]
tensorrt       = "https://github.com/NVIDIA/TensorRT/releases"
torch_tensorrt = "https://github.com/pytorch/TensorRT/releases"
pytorch        = "https://github.com/pytorch/pytorch/releases"
executorch     = "https://github.com/pytorch/executorch/releases"
```

## Section Definitions

### [meta]

| Field | Type | Description |
|---|---|---|
| `last_checked` | ISO 8601 UTC | Timestamp of the most recent //versions:check run |
| `last_benchmarked` | ISO 8601 UTC | Timestamp of the most recent run that produced a valid result |

### [runtimes]

Flat key = value mapping of runtime name → installed version string.
Versions are exactly as reported by `runtime.version()` inside the container.
All runtimes listed in RUNTIMES.md must appear here; //ci:lint enforces this.

### [docker]

| Field | Description |
|---|---|
| `image` | Docker image name and tag (informational only — tag is mutable) |
| `digest` | Full image digest (`sha256:...`) — this is the authoritative identifier. Empty string before the first `//docker:push`; required once any result files exist. |
| `cuda` | CUDA version baked into the image |
| `jetpack` | JetPack version baked into the image |

**Image digest, not tag, is always recorded.** Tags are mutable; a digest is not.
Results include `docker_image` set to this digest (see OBSERVABILITY.md).

### [sources]

Authoritative URLs for where each runtime's releases are published. These are
the URLs //versions:check fetches to detect new upstream versions. Every runtime
in `[runtimes]` that has an upstream release page must have an entry here.
`cuda` and `jetpack` are managed via the Docker image and do not require a
`[sources]` entry. Runtimes bundled inside another runtime (e.g. `aot_inductor`
bundled with PyTorch) share the parent's `[sources]` entry and do not need their
own. `torch_tensorrt` is a separate package with its own release page and has
its own `[sources]` entry.

## Docker Image Rebuild Trigger

A Docker image rebuild is required — and must happen before the next benchmark
run — when any of the following change in versions.toml:

- `[runtimes].cuda`
- `[runtimes].jetpack`
- any `cudnn` entry (if added)

Changes to Python-level runtimes (tensorrt, pytorch, executorch) do not require
an image rebuild; they are installed inside the existing image via pip or wheel.

When a rebuild is required:
1. Update versions.toml with new cuda/jetpack/cudnn values
2. Run `//docker:build` to build the new image
3. Run `//docker:push` to push it to the registry
4. Update `[docker].digest` in versions.toml with the new digest
5. Commit versions.toml before running any benchmark targets

## Update Rules

1. //versions:check runs first in every agent session
2. It reads versions from inside the running Docker container
3. It diffs against the current versions.toml
4. If any version changed, a new benchmark run is triggered automatically
5. After a successful benchmark run, versions.toml is updated and committed
   alongside the new results/
6. versions.toml is never manually edited — it is always written by //versions:check
   (except [sources] and the initial seed value for a new runtime in [runtimes],
   both of which are edited manually when onboarding a new runtime)

## Tracking New Runtimes

When //versions:check discovers a runtime not yet in RUNTIMES.md, it triggers
agent escalation (see AGENT_LOOP.md escalation criteria). New runtimes are not
auto-added — a human must approve the addition to RUNTIMES.md and [sources] first.

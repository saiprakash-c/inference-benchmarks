# ARCHITECTURE

High-level system design for the inference-benchmarks pipeline.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          docker/                                │
│  Execution environment: CUDA · TRT · PyTorch · ExecuTorch       │
│  Runs on Thor (Jetson). Digest pinned in versions.toml.         │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  inputs/ │  │  models/ │  │hardware/ │  │versions/ │       │
│  │          │  │          │  │          │  │          │       │
│  │ ImageNet │  │ ResNet50 │  │ Thor     │  │ check.py │       │
│  │ pipeline │  │ spec     │  │ hw_id    │  │ (diff)   │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┘       │
│       │             │             │                             │
│       └─────────────▼─────────────┘                             │
│                     │                                           │
│               ┌─────▼──────┐                                    │
│               │ runtimes/  │                                    │
│               │            │                                    │
│               │ pytorch    │                                    │
│               │ tensorrt   │                                    │
│               │ executorch │                                    │
│               │ aot_indctr │                                    │
│               └─────┬──────┘                                    │
│                     │                                           │
│               ┌─────▼──────┐                                    │
│               │ benchmark/ │  ← //benchmark:run                 │
│               │ runner.py  │                                    │
│               └─────┬──────┘                                    │
└─────────────────────┼───────────────────────────────────────────┘
                      │
               ┌──────▼──────┐
               │  results/   │  append-only JSON files
               └──────┬──────┘
                      │
               ┌──────▼──────┐
               │   site/     │  → GitHub Pages
               └─────────────┘
```

Operational packages (`lib/`, `tools/`, `ci/`) provide cross-cutting utilities
and are not part of the data pipeline.

---

## Components

### `inputs/`
ImageNet preprocessing pipeline. Resizes, crops, and normalises images to the
float32 tensors that ImageNet-trained models expect. Used by `benchmark/runner.py`
to prepare inputs before any runtime handles them.

### `models/`
Model metadata only: name, task, input shape, weights identifier, benchmark
protocol (warmup/measure iters), and path to the canonical sample image.
No framework code lives here — loading and execution are the runtime's job.

### `hardware/`
Hardware identification and GPU introspection for Thor.
Provides `hw_id()` (returns `"thor"`) and `gpu_info()` (from `nvidia-smi`).
Populated into every result JSON so runs are fully traceable to hardware.

### `runtimes/`
Runtime adapters. Each runtime subclasses `RuntimeBase` (`runtimes/base.py`)
and implements four methods: `init`, `run`, `teardown`, `version`.
A runtime only knows how to load a model and execute inference on a tensor —
it does not know about models, inputs, or hardware.

### `benchmark/`
Orchestration only. `runner.py` coordinates all upstream components:
loads model spec, loads input via `inputs/`, detects hardware via `hardware/`,
initialises the runtime, runs warmup + measurement, computes p50/p99,
and writes a result JSON to `results/`.

### `docker/`
Execution environment. The benchmark image is built once and pinned by
digest in `versions.toml`. All GPU workloads run inside this container on
Thor. `//docker:build` and `//docker:push` manage the image lifecycle.

### `results/`
Append-only flat JSON files, one per `(runtime, model, precision, timestamp)`.
Never mutated after creation. Stored in Git LFS — git history holds pointer
commits; LFS holds the actual content.

### `site/`
Static website generated from `results/`. `//site:build` reads all result
JSON and renders `site/public/index.html`. `//site:deploy` pushes to
the `gh-pages` branch → GitHub Pages.

---

## Forward-Only Export

**Rule:** a component may only import from components upstream of it in the
diagram above. No backwards or sideways imports.

| Component | May import from |
|---|---|
| `inputs/` | `lib/` only |
| `models/` | `lib/` only |
| `hardware/` | `lib/` only |
| `runtimes/` | `lib/` only |
| `benchmark/` | `inputs/`, `models/`, `hardware/`, `runtimes/`, `lib/` |
| `site/` | `lib/` only (reads `results/` as files, not as a Python import) |
| `versions/`, `tools/`, `ci/` | `lib/` only (operational, not in data pipeline) |

**Enforcement:** `//ci:lint` checks for forward-only violations on every PR.
Any import that crosses this boundary is a lint error with a remediation message.

---

## Versions and Reproducibility

`versions.toml` is committed with every benchmark run and records:
- `[runtimes]` — exact version of every runtime inside the container
- `[docker]` — image digest (not tag) used for the run
- `[meta]` — timestamps of last check and last benchmark

Every result JSON also embeds `docker_image` (digest) and `sw_versions`,
making each result fully reproducible from the repo state alone.

# Plan: benchmark-core

Status: awaiting approval

---

## Requirements from User

Run real inference benchmarks on ResNet50 with PyTorch and TensorRT runtimes on
Thor, outputting OBSERVABILITY.md-schema result JSON files.

**Registry model:** every model, runtime, input pipeline, and hardware target is
identified by a string key. A benchmark run is fully specified by a config dict.
Adding a new entry requires only registering the new key — no changes to the runner.

**Runtimes:** `pytorch` (eager mode) and `tensorrt` (compiled engine). Each
implements the four-method interface in `runtimes/base.py`.

**Inputs:** `imagenet` — real ImageNet images, not random tensors. Uses existing
`inputs/imagenet.py` pipeline.

**Hardware:** `thor` — Jetson AGX Orin, via SSH through Tailscale. Execution runs
inside the Docker container using `//tools:ssh_run`.

**Metrics collected:** latency p50/p99 (ms), throughput (samples/sec).

**Output:** one JSON file per `(model, runtime, hardware, timestamp)` in `results/`,
validated by `//tools:validate_results`. `versions.toml` updated after each run.

---

## Updates on User Requirements

**p90 latency dropped:** requirements mention p50/p90/p99, but OBSERVABILITY.md
schema only defines p50 and p99. Following the schema as authoritative — p90
omitted to keep results validatable by `//tools:validate_results`.

**Memory measurement dropped:** requirements mention "memory (MB)" but
OBSERVABILITY.md schema has no memory field. Omitted for schema compliance.
Can be added in a follow-on feature that also extends the schema.

**Open questions resolved:**


| Question                                             | Decision                                                               | Rationale                                                                                                     |
| ---------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Registry: simple dict vs entry-points                | Simple dict in `benchmark/registry.py`                                 | Entry-points require package install machinery; the key set is small and known                                |
| TRT compilation: at load time or separate build step | `init()` time, cached to disk                                          | Compile once per (model, precision), cache at deterministic path; measurement iters never include compilation |
| Batch size                                           | 1 (hardcoded)                                                          | Requirements: "single-sample latency only"                                                                    |
| Warmup / timed iters                                 | From `models/resnet50/spec.py`: `WARMUP_ITERS=10`, `MEASURE_ITERS=100` | Already specified in the model spec                                                                           |


---

## Design

### Component layout

```
benchmark/
  registry.py    ← new: MODEL_REGISTRY, RUNTIME_REGISTRY, INPUT_REGISTRY
  runner.py      ← implement: replaces current scaffold

runtimes/
  pytorch/runtime.py    ← implement: replaces current stub
  tensorrt/runtime.py   ← implement: replaces current stub

results/
  <runtime>_<model>_<hw_id>_<timestamp>.json   ← written per run
```

### Registry

```python
# benchmark/registry.py

from models.resnet50 import spec as resnet50_spec
from runtimes.pytorch.runtime import PyTorchRuntime
from runtimes.tensorrt.runtime import TensorRTRuntime
import inputs.imagenet as imagenet

MODEL_REGISTRY = {
    "resnet50": resnet50_spec,
}

RUNTIME_REGISTRY = {
    "pytorch":   PyTorchRuntime,
    "tensorrt":  TensorRTRuntime,
}

INPUT_REGISTRY = {
    "imagenet": imagenet,
}
```

Hardware is not a registry — `"thor"` maps to `hardware/thor.py` which is always
local (the runner always runs on Thor inside the container).

### BenchmarkConfig

```python
@dataclass
class BenchmarkConfig:
    models:    list[str]   # ["resnet50"]
    runtimes:  list[str]   # ["pytorch", "tensorrt"]
    inputs:    list[str]   # ["imagenet"]
    hardware:  list[str]   # ["thor"]
```

Resolved via registry. Cross-product of `(models × runtimes)` — one run per pair.

### Runner flow (per model × runtime pair)

```
resolve: model_spec, RuntimeClass, input_module from registries
load_input: input_module.load(model_spec.sample_image_path()) → tensor (1,3,224,224)
runtime = RuntimeClass()
engine  = runtime.init(model_path, precision="fp32", device="cuda")

warmup:  runtime.run(engine, tensor, WARMUP_ITERS)   # discard
measure: latencies = runtime.run(engine, tensor, MEASURE_ITERS)  # list[float] ms

p50       = percentile(latencies, 50)
p99       = percentile(latencies, 99)
throughput = 1000.0 / p50   # samples/sec

result = {
  "runtime":      runtime_key,
  "model":        model_key,
  "precision":    "fp32",
  "batch_size":   1,
  "latency_ms":   {"p50": p50, "p99": p99},
  "throughput":   throughput,
  "hw_id":        hw_id(),
  "docker_image": versions_toml["docker"]["digest"],
  "sw_versions":  {runtime_key: runtime.version(), "cuda": ..., "driver": ...},
  "timestamp":    utcnow_iso8601(),
  "status":       "ok",
}

write: results/<runtime>_<model>_<hw_id>_<timestamp>.json
runtime.teardown(engine)
update: versions.toml [meta].last_benchmarked
```

### PyTorch runtime (`runtimes/pytorch/runtime.py`)


| Method     | Implementation                                                                                                   |
| ---------- | ---------------------------------------------------------------------------------------------------------------- |
| `init`     | Load torchvision ResNet50 with `IMAGENET1K_V2` weights; `.eval()`; `.to(device)`                                 |
| `run`      | Loop n_iters: `torch.cuda.synchronize()`, `time.perf_counter()` before/after forward pass; return list[float] ms |
| `teardown` | `del handle`; `torch.cuda.empty_cache()`                                                                         |
| `version`  | `torch.__version_`_                                                                                              |


### TensorRT runtime (`runtimes/tensorrt/runtime.py`)


| Method     | Implementation                                                                                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `init`     | Export model to ONNX (via PyTorch); build TRT engine from ONNX; cache to `/tmp/trt_cache/<model>_<precision>.engine`; allocate CUDA IO buffers; return `(context, buffers)` |
| `run`      | Copy input to GPU buffer; `context.execute_v2()`; `cudart.cudaStreamSynchronize()`; time with `time.perf_counter()`; return list[float] ms                                  |
| `teardown` | Free buffers; del context/engine                                                                                                                                            |
| `version`  | `tensorrt.__version__`                                                                                                                                                      |


Engine cache key: `model_name + "_" + precision`. If cache file exists and is valid,
skip compilation — load directly. This means `init()` is fast on subsequent runs.

### Result filename

```
results/pytorch_resnet50_thor_2026-04-05T120000Z.json
```

Format: `<runtime>_<model>_<hw_id>_<timestamp_compact_utc>.json`

### versions.toml update

After all runs complete, write:

```toml
[meta]
last_benchmarked = "<ISO 8601 UTC>"
```

Runtime versions already present in `[runtimes]` — verify `runtime.version()` matches
and log a warning if not (but do not fail the run).

---

## Tasks

- `benchmark/registry.py` — implement MODEL_REGISTRY, RUNTIME_REGISTRY, INPUT_REGISTRY
- `benchmark/runner.py` — implement full orchestration (replace scaffold)
- `runtimes/pytorch/runtime.py` — implement init/run/teardown
- `runtimes/tensorrt/runtime.py` — implement init/run/teardown with engine caching
- `benchmark/BUILD` — update py_binary deps to include registry and runtime targets
- `versions.toml` update — write `[meta].last_benchmarked` after each run
- `docs/RUNTIMES.md` — update pytorch and tensorrt status from `planned` to `active`
- `docs/MODELS.md` — update ResNet50 status (already `active`, confirm no change needed)

## Updates on Approved Plan

*(append here after approval — never modify sections above)*

**Coding style (approved 2026-04-05):**
- Use `typing` throughout (`list[float]`, `Any`, etc.)
- Explanatory variable names — no single-letter or abbreviated names
- Concise per-function/class docstrings: one line describing what it does; no Args/Returns blocks
- No silent fallbacks — raise or let exceptions propagate; fail loudly
- No `try/except` that swallows errors or returns defaults
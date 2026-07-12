# Design: add-torch-cosmos-reason

## Problem

Cosmos-Reason2-2B is a VLM (vision-language model). It is architecturally
different from the image classification/encoding models already in the registry
(ResNet50, DINOv2):

| | ResNet50 / DINOv2 | Cosmos-Reason2-2B |
|---|---|---|
| Input pipeline | `inputs/` returns a float tensor | processor takes raw image + text |
| Inference call | `model(tensor)` | `model.generate(...)` |
| Output | classification logit / embedding | generated token ids |
| Timing | p50/p99 over 100 iterations | single e2e measurement |
| Metric | `latency_ms.p50`, `throughput` | `e2e_ms`, `output_tokens` |

The design must fit these differences without breaking the existing pipeline and
without modifying `RuntimeBase`.

---

## Component Map

```
models/cosmos_reason2_2b/
  spec.py          ← model metadata (BF16 only, excluded runtimes)
  test_crosswalk.jpg ← committed test image (no runtime fetch)

inputs/cosmos_reason2_2b.py
  load(path) → PIL.Image
  (VLM processor takes raw image, not a pre-normalised tensor)

runtimes/cosmos_pytorch/
  runtime.py       ← CosmosReason2Runtime(RuntimeBase)
    init()         → loads Qwen3VLForConditionalGeneration + AutoProcessor
    run()          → processor call + generate() with CUDA-event timing
                     returns [e2e_ms] (single element); stores last_output_tokens
    teardown()     → del model/processor, cuda.empty_cache()
    version()      → transformers.__version__

benchmark/registry.py
  MODEL_REGISTRY   ← add "cosmos_reason2_2b"
  INPUT_REGISTRY   ← add "cosmos_reason2_2b"
  RUNTIME_REGISTRY ← add "cosmos_pytorch"

benchmark/runner.py
  _run_single_benchmark() — two small additions:
    (a) e2e_ms alias: result["e2e_ms"] = p50_latency  (only for single-iter runs)
    (b) output_tokens: if hasattr(runtime_instance, "last_output_tokens"):
            result["output_tokens"] = runtime_instance.last_output_tokens

versions.toml
  [models.cosmos_reason2_2b] block

docs/MODELS.md, docs/RUNTIMES.md ← new rows
```

---

## Key Design Decisions

### 1. New `cosmos_pytorch` runtime (not reusing `pytorch`)

`PyTorchRuntime` loads models via `models/loader.py` and calls `model(tensor)`.
Reusing it for VLMs would require branching on model type inside a generic runtime —
a violation of the single-responsibility principle. A dedicated `CosmosReason2Runtime`
keeps VLM logic self-contained and leaves `PyTorchRuntime` untouched.

### 2. `inputs/cosmos_reason2_2b.py` returns PIL Image

The HuggingFace processor for Qwen3-VL expects a raw `PIL.Image`, not a
normalised float tensor. Returning the image from the `inputs/` module follows
the existing pattern (one module per model's input prep) while passing the right
type to the runtime.

### 3. Single-iteration timing via CUDA events

Generative models run for seconds per call. Doing 100 iterations (existing
`MEASURE_ITERS`) is impractical. `MEASURE_ITERS = 1`, `WARMUP_ITERS = 1`.
`run()` returns `[e2e_ms]` — a one-element list — so `p50 = p99 = e2e_ms`.
`runner.py` adds `result["e2e_ms"] = p50_latency` for clarity.

### 4. `output_tokens` via instance attribute

`RuntimeBase.run()` returns `list[float]`. Adding a second return value would
require modifying the base class (forbidden). Instead, `CosmosReason2Runtime`
stores `self.last_output_tokens` after each `run()` call, and `runner.py` reads
it with a `hasattr` check. No base class modification needed.

### 5. `"runtime"` label in result JSON

`RUNTIME_REGISTRY` key is `"cosmos_pytorch"`. The result JSON therefore carries
`"runtime": "cosmos_pytorch"`. This is intentional — it distinguishes VLM
PyTorch generation from standard eager PyTorch inference and is unambiguous in
the results store.

---

## What Is NOT in Scope

- TensorRT, Torch-TRT, ExecuTorch, or AOT Inductor paths for this model
- Per-layer profiling (deferred)
- Batch size > 1
- Modifying `RuntimeBase`

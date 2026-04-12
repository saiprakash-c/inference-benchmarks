# Requirements: benchmark-core
Date: 2026-03-29
Status: todo

## Goal
Run real inference benchmarks on ResNet50 with PyTorch and TensorRT runtimes
on Thor, with a registry-based design that makes adding new models, runtimes,
inputs, and hardware a matter of registering a string identifier — not touching
benchmark orchestration code.

## Requirements

### Registry model
- Every model, runtime, input pipeline, and hardware target is identified by a
  string key (e.g. `"resnet50"`, `"pytorch"`, `"imagenet"`, `"thor"`)
- A benchmark run is fully specified by a config:
  ```
  {
    "model":    ["resnet50"],
    "runtime":  ["pytorch", "tensorrt"],
    "input":    ["imagenet"],
    "hardware": ["thor"]
  }
  ```
- The benchmark runner resolves each key to its implementation via a registry;
  adding a new entry requires only registering the new key, not modifying the runner

### Models
- `resnet50`: standard ResNet-50, FP32 precision, real ImageNet inputs
- Model spec defines: name, input shape, precision, pre/post-processing hooks

### Runtimes
- `pytorch`: eager-mode PyTorch inference
- `tensorrt`: TensorRT engine (compiled from the model)
- Runtime contract: `load(model_spec) → engine`, `run(engine, input) → output`,
  `version() → str`

### Inputs
- `imagenet`: real ImageNet validation images (not random tensors)
- Input pipeline contract: `load(n_samples) → List[Tensor]`

### Hardware
- `thor`: the local Jetson AGX Orin dev board, accessed via SSH through Tailscale
- Hardware target defines: how to connect, where to run, what device to use

### Benchmark execution
- Run inside the Docker container on Thor via `//tools:ssh_run`
- Collect: latency (ms, p50/p90/p99), throughput (samples/sec), memory (MB)
- Write result as a JSON file under `results/` following OBSERVABILITY.md schema
- Update `versions.toml` with runtime versions after each run

### Result output
- One JSON file per (model, runtime, hardware, timestamp)
- Schema per OBSERVABILITY.md — validated by `//tools:validate_results`

## Out of scope
- Multi-GPU or batched inference (single-sample latency only for now)
- Models other than ResNet50 (covered by f2 / future features)
- Runtimes other than PyTorch and TensorRT (covered by f2)
- Automated anomaly alerting (already specified in OBSERVABILITY.md)

## Open questions
- Should the registry be a simple dict or use entry-point plugins?
- Where does TensorRT engine compilation happen — at load time or as a separate
  build step cached to disk?
- What batch size for latency measurement: 1, or configurable?
- How many warmup iterations and timed iterations?

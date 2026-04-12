# Requirements: runtime-expansion
Date: 2026-03-29
Status: todo

## Goal
Extend the benchmark registry with ExecuTorch and AOT Inductor runtimes,
running the same ResNet50 / ImageNet benchmark already established by
benchmark-core.

## Requirements
- `executorch`: ExecuTorch runtime, registered under key `"executorch"`
- `aot_inductor`: AOT Inductor (bundled with PyTorch), registered under
  key `"aot_inductor"`
- Both runtimes must satisfy the same runtime contract defined in benchmark-core:
  `load(model_spec) → engine`, `run(engine, input) → output`, `version() → str`
- Results written to `results/` with the same schema as benchmark-core results
- `versions.toml` [runtimes] already tracks both — implementations must match
  the documented versions

## Dependencies
- benchmark-core must be complete before this feature begins

## Out of scope
- New models or inputs (ResNet50 + ImageNet only, same as benchmark-core)
- New hardware targets

## Open questions
- ExecuTorch export path: XNNPACK delegate, CoreML, or custom op backend?
- AOT Inductor: does compilation happen at load time or as a cached artifact?
- Are there version constraints between ExecuTorch and the PyTorch wheel already
  in the Docker image?

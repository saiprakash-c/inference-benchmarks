# RUNTIMES

Pluggability contract for inference runtimes.

## Interface

Every runtime implementation must expose the following four operations:

| Method | Signature | Description |
|---|---|---|
| `init` | `(model_path, precision, device) → handle` | Load model, allocate resources |
| `run` | `(handle, input_tensor, n_iters) → [latency_ms]` | Execute inference n_iters times, return per-iter latency list |
| `teardown` | `(handle) → None` | Release all resources |
| `version` | `() → str` | Return installed runtime version string |

All four methods are required. A missing method is a lint error caught by //ci:lint.

## Adding a New Runtime

1. Create `//runtimes/<name>/` — a directory containing at minimum:
   - `runtime.py` implementing the four-method interface
   - `BUILD` file declaring the Bazel target
2. Add an entry to this file (RUNTIMES.md) in the table below
3. Run //ci:lint locally to verify the entry is consistent

Nothing else in the core harness changes. The benchmark runner discovers runtimes
via the registry populated from this table.

## llms.txt Convention

Each runtime entry below specifies a `docs_url`. When an agent session needs
runtime-specific documentation, it fetches the docs at that URL and caches the
result under `docs/references/<name>/`. Cached references are never committed
as stubs — they are fetched lazily at runtime and may be refreshed by re-running
//versions:check.

## Supported Runtimes

| Name | Target | docs_url | Status |
|---|---|---|---|
| pytorch | `//runtimes/pytorch/` | https://pytorch.org/docs/stable/ | active |
| tensorrt | `//runtimes/tensorrt/` | https://docs.nvidia.com/deeplearning/tensorrt/developer-guide/ | active |
| executorch | `//runtimes/executorch/` | https://pytorch.org/executorch/stable/ | active |
| aot_inductor | `//runtimes/aot_inductor/` | https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/torch.compiler_aot_inductor.html | active |

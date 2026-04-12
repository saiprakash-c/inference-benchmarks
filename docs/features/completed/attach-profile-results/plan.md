# Plan: attach-profile-results
Status: in progress

---

## Requirements from User

- By default, every benchmark run generates layer-by-layer profiling results per `(runtime, model, precision)`.
- The website gets a new column that links to the profile `.txt` file, viewable directly in the browser.

## Updates on User Requirements

- Profile files stored in `results/profiles/` (already LFS-tracked in `.gitattributes`).
- Profiling runs as a separate single-inference pass *after* measurement so p50/p99 are unaffected.
- If profiling fails for a runtime, the benchmark result is still written; `profile_file` is `null`.
- Old result JSONs (without `profile_file`) render `—` in the site table — no backfill needed.

## Design

```
runtimes/base.py
  + profile(handle, input_tensor) -> str | None   ← default returns None

runtimes/*/runtime.py  (all 5 runtimes)
  + override profile()

                     profile text
                          │
benchmark/runner.py ──────┤
  _run_single_benchmark() │
    → runtime.profile()   │
    → _write_profile_txt()│──► results/profiles/<stem>.txt  (LFS)
    → _write_result_json()│──► results/<stem>.json  +  "profile_file" field

site/build.py
  + copy_profiles()  ──────► site/public/profiles/<stem>.txt

site/templates/index.html
  + Profile column  ──────► <a href="/profiles/<stem>.txt">view</a>
```

**File naming:** same stem as the paired JSON.
```
results/pytorch_resnet50_fp32_thor_20260412T015449Z.json
results/profiles/pytorch_resnet50_fp32_thor_20260412T015449Z.txt
```

**Per-runtime profiling:**

| Runtime | Mechanism |
|---|---|
| pytorch | `torch.autograd.profiler.profile(use_cuda=True)` → `.key_averages().table()` |
| tensorrt | Subclass `trt.IProfiler`, attach to context, run one iter, collect per-layer ms |
| torch_tensorrt | `torch.profiler.profile(ProfilerActivity.CUDA)` → `.key_averages().table()` |
| executorch | `torch.profiler.profile(ProfilerActivity.CPU)` → `.key_averages().table()` |
| aot_inductor | `torch.profiler.profile(ProfilerActivity.CUDA)` → `.key_averages().table()` |

## Tasks

- [ ] `runtimes/base.py` — add optional `profile(handle, input_tensor) -> str | None` with default `return None`
- [ ] `runtimes/pytorch/runtime.py` — implement `profile()` using `torch.autograd.profiler`
- [ ] `runtimes/tensorrt/runtime.py` — implement `profile()` using `trt.IProfiler` subclass
- [ ] `runtimes/torch_tensorrt/runtime.py` — implement `profile()` using `torch.profiler`
- [ ] `runtimes/executorch/runtime.py` — implement `profile()` using `torch.profiler`
- [ ] `runtimes/aot_inductor/runtime.py` — implement `profile()` using `torch.profiler`
- [ ] `benchmark/runner.py` — call `runtime.profile()` after measurement; write `.txt` to `results/profiles/`; add `profile_file` field to result JSON
- [ ] `site/build.py` — add `copy_profiles()` to copy `results/profiles/*.txt` → `site/public/profiles/`
- [ ] `site/templates/index.html` — add Profile column with conditional `view` link
- [ ] Write `summary.md`

## Updates on Approved Plan
_(append here after approval — never modify sections above)_

# Summary: attach-profile-results
Completed: 2026-04-12

## What was built

- **`RuntimeBase.profile()`** — an optional method added to `runtimes/base.py` that accepts `(handle, input_tensor)` and returns `str | None`. The default implementation returns `None`, allowing runtimes to opt in without breaking existing ones.
- **Per-runtime implementations** — all five active runtimes override `profile()`:
  - `pytorch`: uses `torch.autograd.profiler.profile(use_cuda=True)`, returns `key_averages().table(sort_by="cuda_time_total")`.
  - `tensorrt`: subclasses `trt.IProfiler`, attaches it to the execution context, runs one inference, and emits a custom `layer name · ms` table.
  - `torch_tensorrt` and `aot_inductor`: use `torch.profiler.profile(ProfilerActivity.CUDA)`, returning `key_averages().table(sort_by="cuda_time_total")`.
  - `executorch`: uses `torch.profiler.profile(ProfilerActivity.CPU)`, returning `key_averages().table(sort_by="cpu_time_total")`.
- **Benchmark runner integration** — `benchmark/runner.py` calls `runtime.profile()` in a separate single-inference pass after the measurement pass, so p50/p99 latencies are unaffected. On success, the profile text is written to `results/profiles/<stem>.txt` and the result JSON gains a `"profile_file": "<stem>.txt"` field. If profiling raises, the exception is caught, logged as a warning, and `profile_file` is set to `null`; the benchmark result is written normally.
- **Site changes** — `site/build.py` gained a `copy_profiles()` function that copies `results/profiles/*.txt` to `site/public/profiles/`, copying only files whose stem appears in a current result with a non-null `profile_file`. `site/templates/index.html` gained a "Profile" column that renders a `view` link (targeting `_blank`) when `profile_file` is set, and `—` otherwise. Old result JSONs without the field render `—` with no backfill required.

## Deviations from plan

The implementation was faithful to the plan. One minor addition introduced in a fix pass: a `_make_stem()` helper was extracted in `benchmark/runner.py` to compute the shared filename stem before any file I/O begins. This ensured both the `.json` and `.txt` files receive the identical stem without performing a second write or re-deriving the name independently, which would risk a timestamp skew between the two files.

## Lessons learned

- The stem must be computed once before any file I/O so both the JSON result and the profile `.txt` share the exact same stem. Deriving the stem twice (with separate `datetime.now()` calls) would cause a mismatch; extract it into a helper first.
- TensorRT's `IProfiler` subclass approach gives true per-layer engine timing (reported directly by the TRT runtime), making it the most accurate profiling mechanism available. `torch.profiler` for the other runtimes gives operator-level CUDA/CPU breakdown, which is useful but one level of abstraction above raw layer timing.
- Profile files should be written to a subdirectory (`results/profiles/`) rather than alongside the JSON files so that LFS glob patterns and the site's copy step remain simple and unambiguous.
- Graceful degradation (catch-and-null) is essential: a profiling failure must never suppress the benchmark result that was already measured.

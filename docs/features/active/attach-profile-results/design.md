# Design: attach-profile-results

Date: 2026-04-12

---

## Goal

After every benchmark run, generate a layer-by-layer timing profile for each
`(runtime, model, precision)` combination and expose it as a viewable `.txt`
file linked from the website results table.

---

## Clarifications on User Requirements


| Question                                            | Decision                                                                          |
| --------------------------------------------------- | --------------------------------------------------------------------------------- |
| Where do .txt files reside?                         | `results/profiles/` — already LFS-tracked in `.gitattributes`                     |
| Which runtimes get profiling?                       | All five active runtimes (graceful fallback if unsupported)                       |
| Profile timing: same pass as benchmark or separate? | Separate single-inference pass, run *after* measurement so p50/p99 are unaffected |
| Site serving path?                                  | `site/public/profiles/*.txt` → `/profiles/<file>` on GitHub Pages                 |


---

## Data Flow

```
benchmark/runner.py
  ├─ _run_single_benchmark()        ← existing (unchanged timing logic)
  │     └─ runtime.run(...)         ← warmup + measure (unchanged)
  │
  ├─ [NEW] runtime.profile(handle, input_tensor)
  │     └─ returns str | None
  │
  ├─ [NEW] _write_profile_txt()     ← writes results/profiles/<stem>.txt
  │
  └─ _write_result_json()           ← adds "profile_file": "<stem>.txt" | null
                                       (existing fn, gains one new field)

site/build.py
  ├─ load_results()                 ← picks up "profile_file" field automatically
  ├─ [NEW] copy_profiles()          ← copies results/profiles/*.txt → site/public/profiles/
  └─ render()                       ← passes profile_file through to template

site/templates/index.html
  └─ [NEW] Profile column           ← "view" link if profile_file set, "—" otherwise
```

---

## Interface Extension: `RuntimeBase.profile()`

```python
def profile(self, handle: Any, input_tensor: Any) -> str | None:
    """Run a single profiled inference; return human-readable layer timing text.
    Returns None if this runtime does not support layer-by-layer profiling."""
    return None
```

- Optional override — default returns `None`
- Called once after the measurement pass; does not affect p50/p99
- Returns plain text suitable for viewing in a browser (`text/plain`)

---

## Per-Runtime Profiling Strategy


| Runtime        | Mechanism                                                      | Output style                                      |
| -------------- | -------------------------------------------------------------- | ------------------------------------------------- |
| pytorch        | `torch.autograd.profiler.profile(use_cuda=True)`               | `key_averages().table(sort_by="cuda_time_total")` |
| tensorrt       | Subclass `trt.IProfiler`, attach to context, run one iteration | Custom table: layer name · ms                     |
| torch_tensorrt | `torch.profiler.profile` (ProfilerActivity.CUDA)               | `key_averages().table(sort_by="cuda_time_total")` |
| executorch     | `torch.profiler.profile` (ProfilerActivity.CPU)                | `key_averages().table(sort_by="cpu_time_total")`  |
| aot_inductor   | `torch.profiler.profile` (ProfilerActivity.CUDA)               | `key_averages().table(sort_by="cuda_time_total")` |


---

## File Naming

Profile files use the **same stem** as their paired JSON, in a subdirectory:

```
results/
  pytorch_resnet50_fp32_thor_20260412T015449Z.json
  profiles/
    pytorch_resnet50_fp32_thor_20260412T015449Z.txt
```

The JSON gains one new field:

```json
"profile_file": "pytorch_resnet50_fp32_thor_20260412T015449Z.txt"
```

If profiling fails or returns `None`, the field is `null` and no `.txt` is written.

---

## Result JSON Schema Change

Single additive field — backwards-compatible (old results without the field
render `—` in the Profile column):

```
"profile_file": "<filename>.txt" | null
```

---

## Site Changes

### `site/build.py`

```
copy_profiles(src=results/profiles/, dst=site/public/profiles/)
```

Copies only files whose stem matches a result with a non-null `profile_file`
(avoids copying stale profiles for results no longer in the latest set).

### `site/templates/index.html`

New header column after "Timestamp":

```html
<th>Profile</th>
```

New data cell:

```html
{% if r.profile_file %}
  <td><a href="/profiles/{{ r.profile_file }}" target="_blank">view</a></td>
{% else %}
  <td>—</td>
{% endif %}
```

---

## Forward-Only Compliance

No new cross-component imports. `benchmark/` already imports `runtimes/`.
`site/` reads `results/` as files. `runtimes/` imports only `lib/`.

---

## Failure Handling

- If `run`ing at site-`time.profile()` raises, the exception is caught in `runner.py`,
logged via `L.warn`, and `profile_file` is set to `null` — benchmark
result is still written normally.
- If a `.txt` file is missbuild time (e.g., stale JSON from
before this feature), the template renders `—` — no build failure.


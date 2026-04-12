# Plan: runtime-expansion
Status: awaiting approval

---

## Requirements from User

Add ExecuTorch (`"executorch"`) and AOT Inductor (`"aot_inductor"`) to the
benchmark registry. Both run the same ResNet50 / ImageNet benchmark as
`benchmark-core`. Results written to `results/` with the same OBSERVABILITY.md
schema. No new models, inputs, or hardware targets.

---

## Updates on User Requirements

**Open questions resolved:**

| Question | Decision | Rationale |
|---|---|---|
| ExecuTorch backend | XNNPACK delegate (CPU) | Standard ARM64 path for Jetson; ExecuTorch GPU support is immature. `device` param ignored for ExecuTorch — it always runs CPU |
| AOT Inductor compilation | `init()` time, `.so` cached to disk at `/tmp/aot_cache/<model>_<precision>_<device>.so` | Same pattern as TRT engine caching — compile once, reuse |
| ExecuTorch version constraints | Use `executorch.__version__`; warn on mismatch with versions.toml (same pattern as existing runtimes) | No special handling needed |

---

## Design

### Registry additions (`benchmark/registry.py`)

```python
from runtimes.executorch.runtime import ExecuTorchRuntime
from runtimes.aot_inductor.runtime import AOTInductorRuntime

RUNTIME_REGISTRY = {
    "pytorch":      PyTorchRuntime,
    "tensorrt":     TensorRTRuntime,
    "executorch":   ExecuTorchRuntime,   # ← add
    "aot_inductor": AOTInductorRuntime,  # ← add
}
```

### ExecuTorch runtime (`runtimes/executorch/runtime.py`)

Export path: `torch.export.export` → `to_edge` (XNNPACK delegate) → `.to_executorch()` → cache `.pte`

| Method | Implementation |
|---|---|
| `init` | Export ResNet50 via XNNPACK → save `/tmp/et_cache/<model>_<precision>.pte` (load from cache if present); load with `_load_for_executorch`; return executor handle |
| `run` | `executor.forward((input_tensor.cpu(),))` × n_iters; `time.perf_counter()` before/after; return `list[float]` ms |
| `teardown` | `del handle` |
| `version` | `executorch.__version__` |

Export code:
```python
from torch.export import export as torch_export
from executorch.exir import to_edge, EdgeCompileConfig
from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner

exported = torch_export(model, (dummy_cpu_input,))
edge = to_edge(exported, compile_config=EdgeCompileConfig(_check_ir_validity=False))
et_program = edge.to_backend(XnnpackPartitioner()).to_executorch()
pte_path.write_bytes(et_program.buffer)
```

Load + run:
```python
from executorch.extension.pybindings.portable_lib import _load_for_executorch
executor = _load_for_executorch(str(pte_path))
executor.forward((cpu_tensor,))
```

Cache path: `/tmp/et_cache/<model>_<precision>.pte`

### AOT Inductor runtime (`runtimes/aot_inductor/runtime.py`)

Compile once via `torch._inductor.aot_compile`, cache the `.so`, load with `torch._export.aot_load`.

| Method | Implementation |
|---|---|
| `init` | Compile ResNet50 via `torch._inductor.aot_compile` → cache `.so` at `/tmp/aot_cache/<model>_<precision>_<device>.so`; load with `torch._export.aot_load(so_path, device)`; return callable runner |
| `run` | `runner(device_tensor)` × n_iters; `torch.cuda.synchronize()` before/after; return `list[float]` ms |
| `teardown` | `del handle`; `torch.cuda.empty_cache()` |
| `version` | `torch.__version__` (AOT Inductor is bundled with PyTorch) |

Compile code:
```python
so_path = torch._inductor.aot_compile(
    model,
    (dummy_cuda_input,),
    options={"aot_inductor.output_path": str(cache_path)},
)
runner = torch._export.aot_load(str(so_path), device)
```

Cache path: `/tmp/aot_cache/<model>_<precision>_<device>.so`

---

## Tasks

- [ ] `runtimes/executorch/runtime.py` — implement init/run/teardown with XNNPACK export and `.pte` caching
- [ ] `runtimes/aot_inductor/runtime.py` — implement init/run/teardown with AOT compile and `.so` caching
- [ ] `benchmark/registry.py` — add `ExecuTorchRuntime` and `AOTInductorRuntime` to `RUNTIME_REGISTRY`
- [ ] `docs/RUNTIMES.md` — update executorch and aot_inductor status from `planned` to `active`

## Updates on Approved Plan

_(append here after approval — never modify sections above)_

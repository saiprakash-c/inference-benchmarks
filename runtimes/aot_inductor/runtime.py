"""
runtimes/aot_inductor/runtime.py

AOT Inductor runtime adapter: compiles the model to a .so shared library,
caches it to disk, loads via torch._export.aot_load, and runs timed inference.
"""

import time
from pathlib import Path
from typing import Any

import torch  # type: ignore[import]

from lib import log as L
from models import loader
from runtimes.base import PRECISION_TO_DTYPE, RuntimeBase

AOT_CACHE_DIR = Path("/tmp/aot_cache")


class AOTInductorRuntime(RuntimeBase):
    """Compiles a model via AOT Inductor (.so cached to disk) and runs timed CUDA inference."""

    def init(self, model_path: str, precision: str, device: str) -> Any:
        """Compile model to a .so via AOT Inductor (cached), load and return callable runner."""
        model_name = Path(model_path).stem if model_path else "resnet50"
        cache_path = AOT_CACHE_DIR / f"{model_name}_{precision}_{device}.so"

        from benchmark.registry import MODEL_REGISTRY  # late import to avoid circular deps
        model_spec = MODEL_REGISTRY[model_name]
        compile_options = getattr(model_spec, "AOT_COMPILE_OPTIONS", {})

        if cache_path.exists():
            L.info("aot_inductor.init.cache_hit", so_path=str(cache_path))
            so_path = str(cache_path)
        else:
            L.info("aot_inductor.init.cache_miss", so_path=str(cache_path))
            so_path = _compile_and_cache(model_name, cache_path, device, precision, compile_options)

        runner = torch._export.aot_load(so_path, device)  # type: ignore[attr-defined]
        return {"runner": runner, "dtype": PRECISION_TO_DTYPE[precision], "device": device}

    def run(self, handle: Any, input_tensor: Any, n_iters: int) -> list[float]:
        """Run inference n_iters times with CUDA-synchronised timing; return latencies in ms."""
        device_tensor = input_tensor.to(device=handle["device"], dtype=handle["dtype"])
        runner = handle["runner"]
        latencies: list[float] = []
        for _ in range(n_iters):
            torch.cuda.synchronize()
            start_time = time.perf_counter()
            runner(device_tensor)
            torch.cuda.synchronize()
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000.0)
        return latencies

    def teardown(self, handle: Any) -> None:
        """Delete the runner handle and release CUDA memory."""
        del handle["runner"]
        torch.cuda.empty_cache()

    def version(self) -> str:
        """Return the installed PyTorch version string (AOT Inductor is bundled with PyTorch)."""
        return torch.__version__

    def profile(self, handle: Any, input_tensor: Any) -> str | None:
        """Run one inference under torch.profiler (CUDA activities) and return key_averages table."""
        from torch.profiler import ProfilerActivity, profile as torch_profile

        device_tensor = input_tensor.to(device=handle["device"], dtype=handle["dtype"])
        runner = handle["runner"]
        with torch_profile(activities=[ProfilerActivity.CUDA]) as prof:
            runner(device_tensor)
        return prof.key_averages().table(sort_by="cuda_time_total", row_limit=50)


def _compile_and_cache(model_name: str, cache_path: Path, device: str, precision: str, compile_options: dict) -> str:
    """Compile model via AOT Inductor, write the .so to cache_path, return its path string."""
    from torch.export import export as torch_export  # type: ignore[import]

    dtype = PRECISION_TO_DTYPE[precision]
    model = loader.load(model_name, device).to(dtype=dtype)
    in_shape = loader.input_shape(model_name)
    dummy_input = torch.zeros(*in_shape, dtype=dtype, device=device)

    # Export and compile under inference_mode: disables version tracking so the
    # compiler can eliminate gradient bookkeeping ops from the graph entirely.
    # freezing:                  fold BN params into preceding Conv weights (removes BN kernels)
    # layout_optimization:       keep conv tensors in NHWC throughout, eliminating layout copies
    # coordinate_descent_tuning: lightweight Triton tile search (avoids full max_autotune overhead)
    # Apply inductor config flags (freezing, layout_optimization, etc.) as global
    # config before export — the options dict only handles aot_inductor.* keys.
    import torch._inductor.config as inductor_cfg  # type: ignore[import]
    inductor_flags = {k: v for k, v in compile_options.items()
                      if not k.startswith("aot_inductor.")}
    aot_options = {k: v for k, v in compile_options.items()
                   if k.startswith("aot_inductor.")}

    old_vals = {k: getattr(inductor_cfg, k, None) for k in inductor_flags}
    for k, v in inductor_flags.items():
        setattr(inductor_cfg, k, v)

    try:
        with torch.inference_mode():
            exported_program = torch_export(model, (dummy_input,))
            graph_module = exported_program.module()

        cache_path.parent.mkdir(parents=True, exist_ok=True)

        so_path = torch._inductor.aot_compile(  # type: ignore[attr-defined]
            graph_module,
            (dummy_input,),
            options={"aot_inductor.output_path": str(cache_path), **aot_options},
        )
    finally:
        # Restore original inductor config to avoid polluting other compilations.
        for k, v in old_vals.items():
            if v is None:
                delattr(inductor_cfg, k)
            else:
                setattr(inductor_cfg, k, v)
    L.info("aot_inductor.cache.saved", path=so_path)
    return so_path

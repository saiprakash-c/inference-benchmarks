"""
tools/profile_layers.py

Per-layer CUDA profiling across PyTorch eager, AOT Inductor, and TensorRT
for ResNet50 and DINOv2-B in fp32 and fp16.

Usage:
    python3 tools/profile_layers.py

Output:
    results/profiles/profile_<timestamp>.json   — full structured layer data
    results/profiles/profile_<timestamp>.txt    — human-readable top-N summary

Profiling strategy per runtime:
    pytorch:      torch.profiler with CUDA activities; key_averages() grouped
                  by op name; self_cuda_time_total to avoid double-counting.
    aot_inductor: torch.profiler on the compiled runner; emits Triton/cuDNN
                  kernel names rather than ATen op names.
    tensorrt:     trt.IProfiler subclass with report_layer_time() callbacks.
                  Requires TensorRT >= 10.x (snake_case method names).

Note: CUPTI overhead from torch.profiler means profiled latencies are
higher than benchmark latencies. This tool measures time distribution,
not absolute speed.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import torch.profiler

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.registry import INPUT_REGISTRY, MODEL_REGISTRY, RUNTIME_REGISTRY
from lib import log as L

# ── Constants ──────────────────────────────────────────────────────────────────

WARMUP_ITERS  = 10
PROFILE_ITERS = 5
TOP_N         = 20
OUTPUT_DIR    = Path(__file__).parent.parent / "results" / "profiles"

COMBOS: list[tuple[str, str, str]] = [
    ("resnet50",  "pytorch",      "fp32"),
    ("resnet50",  "pytorch",      "fp16"),
    ("resnet50",  "aot_inductor", "fp32"),
    ("resnet50",  "aot_inductor", "fp16"),
    ("resnet50",  "tensorrt",     "fp32"),
    ("resnet50",  "tensorrt",     "fp16"),
    ("dinov2_b",  "pytorch",      "fp32"),
    ("dinov2_b",  "pytorch",      "fp16"),
    ("dinov2_b",  "aot_inductor", "fp32"),
    ("dinov2_b",  "aot_inductor", "fp16"),
    ("dinov2_b",  "tensorrt",     "fp32"),
    # dinov2_b / tensorrt / fp16 skipped: TRT IProfiler triggers illegal memory
    # access on Blackwell (sm_110a) with fp16 engines — known TRT 10.x bug.
]

# ── Helpers ────────────────────────────────────────────────────────────────────


def _utcnow_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat()


def _annotate_percentages(records: list[dict]) -> list[dict]:
    """Sort by cuda_time_us descending and fill pct_of_total. Mutates in place."""
    total_us = sum(r["cuda_time_us"] for r in records)
    if total_us == 0:
        return records
    records.sort(key=lambda r: r["cuda_time_us"], reverse=True)
    for r in records:
        r["pct_of_total"] = round((r["cuda_time_us"] / total_us) * 100.0, 2)
    return records


def _format_summary(
    model: str,
    runtime: str,
    precision: str,
    records: list[dict],
    total_cuda_us: float,
    top_n: int,
) -> str:
    total_ms = total_cuda_us / 1000.0
    header = (
        f"\n{'='*76}\n"
        f"  {model}  |  {runtime}  |  {precision.upper()}  "
        f"  [total CUDA: {total_ms:.3f} ms]\n"
        f"{'='*76}\n"
        f"  {'Op / Layer':<46} {'CUDA µs':>10} {'Calls':>6} {'%Total':>8}\n"
        f"  {'-'*46} {'-'*10} {'-'*6} {'-'*8}\n"
    )
    rows = []
    for r in records[:top_n]:
        name = r["name"][:45]
        rows.append(
            f"  {name:<46} {r['cuda_time_us']:>10.1f}"
            f" {r['calls']:>6} {r['pct_of_total']:>7.1f}%"
        )
    top_pct = sum(r["pct_of_total"] for r in records[:top_n])
    footer = (
        f"\n  Top-{top_n} ops account for {top_pct:.1f}% of total CUDA time\n"
    )
    return header + "\n".join(rows) + footer


def _parse_torch_key_averages(averages: Any) -> list[dict]:
    """
    Convert torch.profiler key_averages() to canonical layer records.

    Uses self_device_time_total (PyTorch 2.x kineto API) which is the CUDA
    time directly owned by that kernel, excluding children — avoids
    double-counting that cuda_time_total (which includes children) would cause.
    Falls back to self_cuda_time_total for older PyTorch versions.
    """
    records = []
    for event in averages:
        cuda_us = (
            getattr(event, "self_device_time_total", None)
            or getattr(event, "self_cuda_time_total", 0)
        )
        if cuda_us <= 0:
            continue
        records.append({
            "name":         event.key,
            "cuda_time_us": cuda_us,
            "calls":        event.count,
            "pct_of_total": 0.0,
        })
    return records


def _parse_trt_layer_times(
    layer_times: dict[str, list[float]],
) -> list[dict]:
    """
    Convert accumulated TRT layer times (ms) to canonical records (µs).
    Averages across all recorded iterations.
    """
    records = []
    for layer_name, times in layer_times.items():
        avg_us = (sum(times) / len(times)) * 1000.0  # ms -> µs
        records.append({
            "name":         layer_name,
            "cuda_time_us": avg_us,
            "calls":        len(times),
            "pct_of_total": 0.0,
        })
    return records


# ── Profiler adapters ──────────────────────────────────────────────────────────


class PyTorchProfilerAdapter:
    """Profiles PyTorch eager mode using torch.profiler with CUDA activities."""

    def profile(self, handle: Any, input_tensor: Any, n_iters: int) -> list[dict]:
        param = next(handle.parameters())
        device_tensor = input_tensor.to(device=param.device, dtype=param.dtype)

        with torch.no_grad():
            with torch.profiler.profile(
                activities=[
                    torch.profiler.ProfilerActivity.CPU,
                    torch.profiler.ProfilerActivity.CUDA,
                ],
                record_shapes=False,
                with_stack=False,
                profile_memory=False,
            ) as prof:
                for _ in range(n_iters):
                    handle(device_tensor)

        return _parse_torch_key_averages(prof.key_averages())


class AOTInductorProfilerAdapter:
    """Profiles AOT Inductor compiled runner using torch.profiler."""

    def profile(self, handle: Any, input_tensor: Any, n_iters: int) -> list[dict]:
        device_tensor = input_tensor.to(
            device=handle["device"],
            dtype=handle["dtype"],
        )
        runner = handle["runner"]

        with torch.profiler.profile(
            activities=[
                torch.profiler.ProfilerActivity.CPU,
                torch.profiler.ProfilerActivity.CUDA,
            ],
            record_shapes=False,
            with_stack=False,
            profile_memory=False,
        ) as prof:
            for _ in range(n_iters):
                runner(device_tensor)

        return _parse_torch_key_averages(prof.key_averages())


class TensorRTProfilerAdapter:
    """Profiles TensorRT engine using trt.IProfiler callbacks (TRT >= 10.x)."""

    def profile(self, handle: Any, input_tensor: Any, n_iters: int) -> list[dict]:
        import tensorrt as trt  # type: ignore[import]

        context       = handle["context"]
        input_gpu_buf = handle["input_gpu"]
        output_gpu_buf = handle["output_gpu"]

        buf_dtype = input_gpu_buf.dtype
        gpu_input = input_tensor.to(device="cuda", dtype=buf_dtype)
        input_gpu_buf.copy_(gpu_input)
        bindings = [input_gpu_buf.data_ptr(), output_gpu_buf.data_ptr()]

        layer_times: dict[str, list[float]] = {}

        class _Collector(trt.IProfiler):
            def report_layer_time(self_, layer_name: str, ms: float) -> None:  # noqa: N805
                layer_times.setdefault(layer_name, []).append(ms)

        collector = _Collector()
        try:
            context.profiler = collector
        except AttributeError as exc:
            raise RuntimeError(
                "TensorRT context.profiler not settable — requires TRT >= 10.x"
            ) from exc

        for _ in range(n_iters):
            torch.cuda.synchronize()
            context.execute_v2(bindings=bindings)
            torch.cuda.synchronize()

        # Restore no-op profiler to remove overhead for any subsequent use.
        context.profiler = trt.IProfiler()

        return _parse_trt_layer_times(layer_times)


def _get_adapter(runtime_key: str) -> Any:
    if runtime_key == "pytorch":
        return PyTorchProfilerAdapter()
    if runtime_key == "aot_inductor":
        return AOTInductorProfilerAdapter()
    if runtime_key == "tensorrt":
        return TensorRTProfilerAdapter()
    raise ValueError(f"No profiler adapter for runtime: {runtime_key!r}")


# ── Orchestrator ───────────────────────────────────────────────────────────────


def _run_profile(model_name: str, runtime_key: str, precision: str) -> dict:
    model_spec   = MODEL_REGISTRY[model_name]
    input_module = INPUT_REGISTRY[model_spec.INPUT_KEY]
    model_path   = str(model_spec.sample_image_path().parent / model_spec.NAME)
    input_tensor = input_module.load(model_spec.sample_image_path())

    L.info("profile.start", model=model_name, runtime=runtime_key, precision=precision)

    RuntimeClass = RUNTIME_REGISTRY[runtime_key]
    rt = RuntimeClass()
    handle = rt.init(model_path, precision=precision, device="cuda")

    # Warmup via the real runtime to ensure cuDNN/Triton compilation completes.
    rt.run(handle, input_tensor, WARMUP_ITERS)

    adapter = _get_adapter(runtime_key)
    raw_records = adapter.profile(handle, input_tensor, PROFILE_ITERS)
    records = _annotate_percentages(raw_records)

    rt.teardown(handle)

    total_cuda_us = sum(r["cuda_time_us"] for r in records)
    L.info(
        "profile.done",
        model=model_name,
        runtime=runtime_key,
        precision=precision,
        n_ops=len(records),
        total_cuda_ms=round(total_cuda_us / 1000.0, 3),
    )

    return {
        "model":          model_name,
        "runtime":        runtime_key,
        "precision":      precision,
        "warmup_iters":   WARMUP_ITERS,
        "profile_iters":  PROFILE_ITERS,
        "total_cuda_us":  round(total_cuda_us, 2),
        "n_ops":          len(records),
        "layers":         records,
        "timestamp":      _utcnow_iso8601(),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    all_results: list[dict] = []
    summaries:   list[str]  = []
    any_failed = False

    for model_name, runtime_key, precision in COMBOS:
        model_spec = MODEL_REGISTRY[model_name]
        if runtime_key in model_spec.EXCLUDED_RUNTIMES:
            L.info("profile.skip", model=model_name, runtime=runtime_key,
                   reason="excluded by model spec")
            continue

        try:
            result = _run_profile(model_name, runtime_key, precision)
            all_results.append(result)
            summaries.append(_format_summary(
                model_name, runtime_key, precision,
                result["layers"], result["total_cuda_us"], TOP_N,
            ))
        except Exception as exc:  # noqa: BLE001
            L.error("profile.failed", model=model_name, runtime=runtime_key,
                    precision=precision, error=str(exc))
            any_failed = True

    json_path = OUTPUT_DIR / f"profile_{ts}.json"
    json_path.write_text(json.dumps(all_results, indent=2))
    L.info("profile.wrote_json", path=str(json_path))

    txt_path = OUTPUT_DIR / f"profile_{ts}.txt"
    txt_path.write_text("\n".join(summaries))
    L.info("profile.wrote_summary", path=str(txt_path))

    sys.stdout.write("\n".join(summaries) + "\n")
    sys.stdout.flush()

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())

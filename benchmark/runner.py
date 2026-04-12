"""
//benchmark:run

Orchestrates benchmark runs across all registered (model, runtime) pairs.
Writes one OBSERVABILITY.md-schema result JSON per pair to results/.
Updates versions.toml [meta].last_benchmarked after all runs complete.
"""

import json
import statistics
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tomli_w  # type: ignore[import]

from benchmark.registry import INPUT_REGISTRY, MODEL_REGISTRY, RUNTIME_REGISTRY
from hardware.thor import gpu_info, hw_id
from lib import log as L

VERSIONS_TOML_PATH = Path(__file__).parent.parent / "versions.toml"
RESULTS_DIR = Path(__file__).parent.parent / "results"
PROFILES_DIR = RESULTS_DIR / "profiles"


@dataclass
class BenchmarkConfig:
    """Specifies which models, runtimes, and hardware targets to run."""
    models: list[str]
    runtimes: list[str]
    hardware: list[str]


def _utcnow_iso8601() -> str:
    """Return the current UTC time formatted as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _utcnow_compact() -> str:
    """Return the current UTC time as a compact filename-safe string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _compute_percentile(values: list[float], percentile: int) -> float:
    """Compute a given percentile from a list of floats using linear interpolation."""
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    # statistics.quantiles with n=100 gives 99 cut points at positions 1..99.
    quantiles = statistics.quantiles(sorted_values, n=100, method="inclusive")
    return quantiles[percentile - 1]


def _load_versions_toml() -> dict:
    """Load and return the parsed versions.toml as a dict."""
    with VERSIONS_TOML_PATH.open("rb") as toml_file:
        return tomllib.load(toml_file)


def _update_versions_toml_last_benchmarked(timestamp: str) -> None:
    """Write the given ISO 8601 timestamp into versions.toml [meta].last_benchmarked."""
    versions = _load_versions_toml()
    versions["meta"]["last_benchmarked"] = timestamp
    VERSIONS_TOML_PATH.write_bytes(tomli_w.dumps(versions).encode())
    L.info("versions.update", last_benchmarked=timestamp)


def _check_runtime_version(runtime_key: str, runtime_version: str, versions: dict) -> None:
    """Warn if the running runtime version differs from the one recorded in versions.toml."""
    recorded_version = versions.get("runtimes", {}).get(runtime_key)
    if recorded_version and recorded_version != runtime_version:
        L.warn(
            "versions.mismatch",
            runtime=runtime_key,
            recorded=recorded_version,
            running=runtime_version,
        )


def _run_single_benchmark(
    model_key: str,
    runtime_key: str,
    precision: str,
    input_key: str,
    versions: dict,
) -> tuple[dict, str | None]:
    """
    Run warmup and measurement iterations for one (model, runtime, precision) triple.
    Returns a result dict matching the OBSERVABILITY.md schema.
    """
    model_spec = MODEL_REGISTRY[model_key]
    RuntimeClass = RUNTIME_REGISTRY[runtime_key]
    input_module = INPUT_REGISTRY[input_key]

    model_path = str(model_spec.sample_image_path().parent / model_spec.NAME)

    L.info(
        "benchmark.start",
        model=model_key,
        runtime=runtime_key,
        precision=precision,
    )

    input_tensor = input_module.load(model_spec.sample_image_path())

    runtime_instance = RuntimeClass()
    engine_handle = runtime_instance.init(model_path, precision=precision, device="cuda")

    # Warmup — discard latencies.
    runtime_instance.run(engine_handle, input_tensor, model_spec.WARMUP_ITERS)

    # Measurement.
    measured_latencies = runtime_instance.run(
        engine_handle, input_tensor, model_spec.MEASURE_ITERS
    )

    p50_latency = _compute_percentile(measured_latencies, 50)
    p99_latency = _compute_percentile(measured_latencies, 99)
    throughput = 1000.0 / p50_latency

    runtime_version = runtime_instance.version()
    _check_runtime_version(runtime_key, runtime_version, versions)

    hardware_info = gpu_info()
    cuda_version = hardware_info.get("cuda_version", versions.get("runtimes", {}).get("cuda", ""))
    driver_version = hardware_info.get("driver", "")
    docker_image_digest = versions.get("docker", {}).get("digest", "")

    # Profiling — single inference pass after measurement so p50/p99 are unaffected.
    profile_text: str | None = None
    try:
        profile_text = runtime_instance.profile(engine_handle, input_tensor)
    except Exception as exc:  # noqa: BLE001
        L.warn("benchmark.profile_failed", model=model_key, runtime=runtime_key, error=str(exc))

    runtime_instance.teardown(engine_handle)

    result = {
        "runtime": runtime_key,
        "model": model_key,
        "precision": precision,
        "batch_size": 1,
        "latency_ms": {"p50": p50_latency, "p99": p99_latency},
        "throughput": throughput,
        "hw_id": hw_id(),
        "docker_image": docker_image_digest,
        "sw_versions": {
            runtime_key: runtime_version,
            "cuda": cuda_version,
            "driver": driver_version,
        },
        "timestamp": _utcnow_iso8601(),
        "status": "ok",
        "profile_file": None,
    }

    L.info(
        "benchmark.result",
        model=model_key,
        runtime=runtime_key,
        p50_ms=p50_latency,
        p99_ms=p99_latency,
        throughput=throughput,
    )

    return result, profile_text


def _write_profile_txt(profile_text: str, stem: str) -> Path:
    """Write profile text to results/profiles/<stem>.txt and return the path."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = PROFILES_DIR / f"{stem}.txt"
    profile_path.write_text(profile_text)
    L.info("benchmark.profile_write", path=str(profile_path))
    return profile_path


def _write_result_json(result: dict, runtime_key: str, model_key: str) -> Path:
    """Write one result dict to a timestamped JSON file under results/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    hardware_identifier = result["hw_id"]
    precision = result["precision"]
    timestamp_compact = _utcnow_compact()
    stem = f"{runtime_key}_{model_key}_{precision}_{hardware_identifier}_{timestamp_compact}"
    filename = f"{stem}.json"
    output_path = RESULTS_DIR / filename
    output_path.write_text(json.dumps(result, indent=2))
    L.info("benchmark.write", path=str(output_path))
    return output_path, stem


def run(config: BenchmarkConfig) -> int:
    """
    Execute all (model, runtime) pairs in config and write result JSON files.
    Returns 0 on success, 1 if any run fails.
    """
    versions = _load_versions_toml()
    any_failed = False

    for model_key in config.models:
        if model_key not in MODEL_REGISTRY:
            L.error("benchmark.error", message=f"Unknown model key: {model_key}")
            any_failed = True
            continue

        model_spec = MODEL_REGISTRY[model_key]
        input_key = model_spec.INPUT_KEY
        if input_key not in INPUT_REGISTRY:
            L.error("benchmark.error", message=f"Unknown input key: {input_key}")
            any_failed = True
            continue

        for precision in model_spec.SUPPORTED_PRECISIONS:
            for runtime_key in config.runtimes:
                if runtime_key in model_spec.EXCLUDED_RUNTIMES:
                    L.info("benchmark.skip", model=model_key, runtime=runtime_key, precision=precision, reason="excluded by model spec")
                    continue

                if runtime_key not in RUNTIME_REGISTRY:
                    L.error("benchmark.error", message=f"Unknown runtime key: {runtime_key}")
                    any_failed = True
                    continue

                RuntimeClass = RUNTIME_REGISTRY[runtime_key]
                if precision not in RuntimeClass.SUPPORTED_PRECISIONS:
                    L.info("benchmark.skip", model=model_key, runtime=runtime_key, precision=precision, reason="precision not supported by runtime")
                    continue

                try:
                    result, profile_text = _run_single_benchmark(model_key, runtime_key, precision, input_key, versions)
                    output_path, stem = _write_result_json(result, runtime_key, model_key)
                    if profile_text is not None:
                        _write_profile_txt(profile_text, stem)
                        # Patch profile_file into the JSON now that we know the stem.
                        result["profile_file"] = f"{stem}.txt"
                        output_path.write_text(json.dumps(result, indent=2))
                except Exception as exc:  # noqa: BLE001
                    L.error("benchmark.failed", model=model_key, runtime=runtime_key, precision=precision, error=str(exc))
                    any_failed = True

    completion_timestamp = _utcnow_iso8601()
    _update_versions_toml_last_benchmarked(completion_timestamp)

    return 1 if any_failed else 0


def main() -> int:
    """Entry point: run benchmarks with the default full configuration."""
    default_config = BenchmarkConfig(
        models=list(MODEL_REGISTRY.keys()),
        runtimes=list(RUNTIME_REGISTRY.keys()),
        hardware=["thor"],
    )
    return run(default_config)


if __name__ == "__main__":
    sys.exit(main())

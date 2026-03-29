# OBSERVABILITY

Structured log format for agent parseability and anomaly detection.

## Result Schema

Every benchmark result must be a JSON object with the following mandatory fields.
A result missing any field is a schema error and must not be committed.

```json
{
  "runtime": "<string>",
  "model": "<string>",
  "precision": "<fp32>",
  "batch_size": <int>,
  "latency_ms": {
    "p50": <float>,
    "p99": <float>
  },
  "throughput": <float>,
  "hw_id": "<string>",
  "docker_image": "<sha256:...>",
  "sw_versions": {
    "<runtime_name>": "<version_string>",
    "cuda": "<version_string>",
    "driver": "<version_string>"
  },
  "timestamp": "<ISO 8601>",
  "status": "<ok|error|anomaly>"
}
```

### Field Definitions

| Field | Type | Description |
|---|---|---|
| `runtime` | string | Runtime name matching RUNTIMES.md registry |
| `model` | string | Model name matching MODELS.md registry |
| `precision` | enum | `fp32` (active); fp16/int8/fp8 planned |
| `batch_size` | int | Batch size used during measurement |
| `latency_ms.p50` | float | Median inference latency in milliseconds |
| `latency_ms.p99` | float | 99th percentile latency in milliseconds |
| `throughput` | float | Inferences per second at sustained load |
| `hw_id` | string | Hardware identifier (e.g. `thor`) |
| `docker_image` | string | Full image digest (`sha256:...`) from versions.toml `[docker].digest` |
| `sw_versions` | dict | Mapping of component name → version string |
| `timestamp` | ISO 8601 | UTC timestamp when the run completed |
| `status` | enum | One of: ok, error, anomaly |

`docker_image` must be the full digest, never a tag. It must match `[docker].digest`
in the versions.toml committed alongside the result.

## Anomaly Thresholds

`//tools:validate_results` enforces these thresholds automatically:

| Condition | Field set to | Agent action |
|---|---|---|
| Latency regression >20% vs last run | `status: anomaly` | Re-run once, then escalate if persistent |
| NaN or null in any numeric field | `status: error` | Re-run once, then escalate if persistent |
| hw_id mismatch vs expected target | `status: error` | Escalate immediately, do not re-run |
| docker_image digest mismatch vs versions.toml | `status: error` | Escalate immediately, do not re-run |

A docker_image digest mismatch means the container that ran the benchmark is not
the container recorded in versions.toml. This indicates an environment integrity
problem and requires human review — results from a mismatched container are not
valid and must not be merged.

## TRT Profiler Output

TensorRT profiler output (trt-exec profile JSON) must be parsed and summarized
into the result schema above before being committed. Raw profiler output is not
a valid result. `//tools:validate_results` rejects raw profiler dumps.

## Structured Logging

All Python targets use structured logging (JSON lines to stdout).
No `print()` calls are permitted — this is enforced by a Bazel lint.

Log line format for benchmark events:

```json
{"level": "INFO", "event": "<event_name>", "ts": "<ISO 8601>", "data": {...}}
```

Standard event names:
- `benchmark.start` — beginning of a run
- `benchmark.result` — one completed result record
- `benchmark.anomaly` — anomaly detected, with details
- `benchmark.error` — error encountered, with full traceback in `data.traceback`
- `versions.check` — output of //versions:check
- `validate.pass` — schema validation passed
- `validate.fail` — schema validation failed, with field path and reason
- `docker.digest_mismatch` — docker_image in result does not match versions.toml

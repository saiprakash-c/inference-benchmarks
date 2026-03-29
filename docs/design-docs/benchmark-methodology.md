# Benchmark Methodology

How results are collected, validated, and stored.

## Run Sequence

1. //versions:check detects installed runtime versions and diffs against versions.toml
2. If any version changed (or --force passed): //benchmark:run executes the full suite
3. //tools:validate_results checks every result JSON against the schema in OBSERVABILITY.md
4. Validated results are appended to results/ (append-only; no mutation of existing files)
5. versions.toml is updated and committed alongside results/

## Measurement Protocol

- Warmup: minimum 10 inferences discarded before measurement begins
- Sample size: 100 inferences per (runtime, model, precision) combination
- Reported latency: p50 and p99 (ms), not mean — means hide tail behavior
- Reported throughput: inferences per second at sustained load
- Each run records: runtime, model, precision, batch_size, latency_ms (p50/p99),
  throughput, hw_id, sw_versions, timestamp, status

## Precision Variants

FP32 is the active precision. Others are planned but not yet in scope:
- FP32 (active)
- FP16 (planned)
- INT8 (planned — requires calibration dataset)
- FP8 (planned — requires Hopper/Blackwell hardware)

## Hardware

Target platform: Thor.
All benchmark runs execute on Thor via `//tools:ssh_run` inside the Docker container.
Other hardware targets (e.g. Jetson AGX Orin) are out of scope for now.

hw_id is recorded per result. Results from unexpected hardware IDs trigger
escalation per AGENT_LOOP.md.

## Anomaly Detection

Handled by //tools:validate_results per thresholds in OBSERVABILITY.md:
- >20% latency regression vs. last passing run → status: anomaly
- NaN or null in any numeric field → status: error
- hw_id mismatch vs. expected target → status: error

Anomalous runs are re-run once automatically. Persistent anomalies escalate
to human review with a specific description of what was unexpected.

## Result Storage

- Flat JSON files under results/, one file per (runtime, model, precision, timestamp)
- results/ is append-only — no existing file is ever mutated
- This invariant is enforced by a Bazel lint (//ci:lint)

"""
//tools:validate_results

Validates result JSON files against the schema defined in docs/OBSERVABILITY.md.

Usage:
  bazel run //tools:validate_results -- results/          # validate a directory
  bazel run //tools:validate_results -- results/foo.json  # validate a single file

Exit codes:
  0 — all results valid
  1 — one or more schema violations or anomalies detected
  2 — usage error or unreadable file
"""

import json
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

# ── Schema ─────────────────────────────────────────────────────────────────────

RESULT_SCHEMA = {
    "type": "object",
    "required": [
        "runtime",
        "model",
        "precision",
        "batch_size",
        "latency_ms",
        "throughput",
        "hw_id",
        "docker_image",
        "sw_versions",
        "timestamp",
        "status",
    ],
    "properties": {
        "runtime":       {"type": "string", "minLength": 1},
        "model":         {"type": "string", "minLength": 1},
        "precision":     {"type": "string", "enum": ["fp32", "fp16", "int8", "fp8"]},
        "batch_size":    {"type": "integer", "minimum": 1},
        "latency_ms": {
            "type": "object",
            "required": ["p50", "p99"],
            "properties": {
                "p50": {"type": "number", "exclusiveMinimum": 0},
                "p99": {"type": "number", "exclusiveMinimum": 0},
            },
            "additionalProperties": False,
        },
        "throughput":    {"type": "number", "exclusiveMinimum": 0},
        "hw_id":         {"type": "string", "minLength": 1},
        "docker_image":  {"type": "string", "pattern": r"^sha256:[a-f0-9]{64}$"},
        "sw_versions": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string"},
        },
        "timestamp":     {"type": "string", "format": "date-time"},
        "status":        {"type": "string", "enum": ["ok", "error", "anomaly"]},
    },
    "additionalProperties": False,
}

validator = jsonschema.Draft7Validator(RESULT_SCHEMA)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        return json.loads(path.read_text()), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    except OSError as exc:
        return None, f"cannot read file: {exc}"


def _validate_file(path: Path) -> bool:
    data, read_err = _load_json(path)
    if read_err:
        L.error("validate.fail", file=str(path), reason=read_err)
        return False

    errors = list(validator.iter_errors(data))
    if errors:
        for err in errors:
            L.error(
                "validate.fail",
                file=str(path),
                field=list(err.absolute_path),
                reason=err.message,
            )
        return False

    # Extra numeric sanity: catch NaN/Inf that JSON schema won't catch
    # (jsonschema passes Python float('nan') since it's type "number")
    p50 = data["latency_ms"]["p50"]
    p99 = data["latency_ms"]["p99"]
    throughput = data["throughput"]
    for name, val in [("latency_ms.p50", p50), ("latency_ms.p99", p99), ("throughput", throughput)]:
        if not (val == val) or val != val:  # NaN check
            L.error("validate.fail", file=str(path), field=name, reason="NaN")
            return False

    L.info("validate.pass", file=str(path), runtime=data["runtime"], model=data["model"])
    return True


# ── Main ───────────────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        L.error("validate.fail", reason="usage: validate_results <path>")
        return 2

    target = Path(argv[1])
    if not target.exists():
        L.error("validate.fail", reason=f"path does not exist: {target}")
        return 2

    if target.is_file():
        paths = [target]
    else:
        paths = sorted(target.rglob("*.json"))

    if not paths:
        L.warn("validate.pass", reason="no result files found", path=str(target))
        return 0

    failures = [p for p in paths if not _validate_file(p)]

    if failures:
        L.error(
            "validate.fail",
            total=len(paths),
            failed=len(failures),
            failed_files=[str(p) for p in failures],
        )
        return 1

    L.info("validate.pass", total=len(paths), all_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

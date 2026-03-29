"""
//site:build

Reads all JSON files from results/, aggregates by (runtime, model),
and renders a static HTML site to site/public/.

Usage:
  bazel run //site:build
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "results"
TEMPLATES_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = REPO_ROOT / "site" / "public"


# ── Data loading ───────────────────────────────────────────────────────────────


def load_results() -> list[dict]:
    results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            results.append(data)
        except Exception as exc:
            L.warn("site.build", file=str(path), skipped=True, reason=str(exc))
    return results


def aggregate(results: list[dict]) -> dict:
    """
    Returns a nested dict:
      { runtime: { model: [result, ...] } }
    sorted by (runtime, model).
    """
    agg: dict[str, dict[str, list[dict]]] = {}
    for r in results:
        runtime = r.get("runtime", "unknown")
        model = r.get("model", "unknown")
        agg.setdefault(runtime, {}).setdefault(model, []).append(r)

    # Sort each model's results by timestamp descending
    for runtime in agg:
        for model in agg[runtime]:
            agg[runtime][model].sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return dict(sorted(agg.items()))


def latest_per_combo(agg: dict) -> list[dict]:
    """Flat list of the most recent result per (runtime, model)."""
    rows = []
    for runtime, models in agg.items():
        for model, results in models.items():
            if results:
                rows.append(results[0])
    return sorted(rows, key=lambda r: (r["runtime"], r["model"]))


# ── Rendering ──────────────────────────────────────────────────────────────────


def render(results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    agg = aggregate(results)
    rows = latest_per_combo(agg)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    tmpl = env.get_template("index.html")
    html = tmpl.render(rows=rows, agg=agg, generated_at=generated_at)

    out = OUTPUT_DIR / "index.html"
    out.write_text(html)
    L.info("site.build", output=str(out), result_count=len(rows))


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    results = load_results()
    L.info("site.build", loaded=len(results))

    if not results:
        L.warn("site.build", reason="no result files found in results/ — building empty site")

    render(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())

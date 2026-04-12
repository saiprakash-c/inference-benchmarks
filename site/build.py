"""
//site:build

Reads all JSON files from results/, aggregates by (runtime, model),
and renders a static HTML site to site/public/.

Usage:
  bazel run //site:build
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "results"
PROFILES_DIR = RESULTS_DIR / "profiles"
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
      { (model, precision): { runtime: [result, ...] } }
    sorted by (model, precision, runtime).
    """
    agg: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for r in results:
        model = r.get("model", "unknown")
        precision = r.get("precision", "fp32")
        runtime = r.get("runtime", "unknown")
        agg.setdefault((model, precision), {}).setdefault(runtime, []).append(r)

    # Sort each runtime's results by timestamp descending
    for key in agg:
        for runtime in agg[key]:
            agg[key][runtime].sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return dict(sorted(agg.items()))


def latest_per_combo(agg: dict) -> dict:
    """
    Returns sections for the template:
      { (model, precision): [latest result per runtime, ...] }
    rows within each section sorted by runtime name.
    """
    sections = {}
    for (model, precision), runtimes in agg.items():
        rows = []
        for runtime, results in runtimes.items():
            if results:
                rows.append(results[0])
        sections[(model, precision)] = sorted(rows, key=lambda r: r["runtime"])
    return dict(sorted(sections.items()))


# ── Profile copying ────────────────────────────────────────────────────────────


def copy_profiles(results: list[dict]) -> None:
    """
    Copy profile .txt files referenced by at least one result into
    site/public/profiles/. Only copies files that are actually referenced
    (avoids copying stale profiles).
    """
    dest_dir = OUTPUT_DIR / "profiles"
    referenced = {r["profile_file"] for r in results if r.get("profile_file")}
    if not referenced:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for filename in referenced:
        src = PROFILES_DIR / filename
        if src.exists():
            shutil.copy2(src, dest_dir / filename)
            copied += 1
        else:
            L.warn("site.build.profile_missing", file=str(src))
    L.info("site.build.profiles_copied", count=copied, dest=str(dest_dir))


# ── Rendering ──────────────────────────────────────────────────────────────────


def render(results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    copy_profiles(results)

    agg = aggregate(results)
    sections = latest_per_combo(agg)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    tmpl = env.get_template("index.html")
    html = tmpl.render(sections=sections, generated_at=generated_at)

    out = OUTPUT_DIR / "index.html"
    out.write_text(html)
    total = sum(len(rows) for rows in sections.values())
    L.info("site.build", output=str(out), result_count=total)


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

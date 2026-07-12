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
      { model: { (runtime, precision): [result, ...] } }
    sorted by model.
    """
    agg: dict[str, dict[tuple[str, str], list[dict]]] = {}
    for r in results:
        model = r.get("model", "unknown")
        precision = r.get("precision", "fp32")
        runtime = r.get("runtime", "unknown")
        agg.setdefault(model, {}).setdefault((runtime, precision), []).append(r)

    # Sort each (runtime, precision)'s results by timestamp descending
    for model in agg:
        for key in agg[model]:
            agg[model][key].sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return dict(sorted(agg.items()))


def latest_per_combo(agg: dict) -> dict:
    """
    Returns sections for the template:
      { model: [latest result per (runtime, precision), ...] }
    rows within each section sorted by (runtime, precision).
    """
    sections = {}
    for model, combos in agg.items():
        rows = []
        for (runtime, precision), results in combos.items():
            if results:
                rows.append(results[0])
        sections[model] = sorted(rows, key=lambda r: (r["runtime"], r.get("precision", "")))
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


def _split_sections(sections: dict) -> tuple[dict, dict]:
    """
    Split sections into vision and VLM buckets.
    VLM results have lingo_judge_mean not None in at least one row.
    """
    vision: dict = {}
    vlm: dict = {}
    for model, rows in sections.items():
        if any(r.get("lingo_judge_mean") is not None for r in rows):
            vlm[model] = rows
        else:
            vision[model] = rows
    return vision, vlm


def render(results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    copy_profiles(results)

    agg = aggregate(results)
    all_sections = latest_per_combo(agg)
    vision_sections, vlm_sections = _split_sections(all_sections)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    tmpl = env.get_template("index.html")
    html = tmpl.render(
        vision_sections=vision_sections,
        vlm_sections=vlm_sections,
        generated_at=generated_at,
    )

    out = OUTPUT_DIR / "index.html"
    out.write_text(html)
    total = sum(len(rows) for rows in all_sections.values())
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

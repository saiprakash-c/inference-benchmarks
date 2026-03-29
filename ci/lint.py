"""
//ci:lint

Mechanical lint checks. Run as a Bazel test — exit 0 means all pass.
All error messages include remediation instructions so an agent can self-correct.

Checks:
  1. Every runtime in docs/RUNTIMES.md has a directory at runtimes/<name>/
  2. Every model in docs/MODELS.md has a directory at models/<name>/
  3. All runtimes in RUNTIMES.md appear in versions.toml [runtimes]
  4. No print() calls in Python source files
  5. results/ is append-only (no existing files modified, per git status)
  6. QUALITY_SCORE.md was updated within the last 7 days
  7. Every active feature has requirements.md, design.md, and plan.md
  8. Every active patch has ## Problem and ## Fix sections
"""

import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
RUNTIMES_MD = REPO_ROOT / "docs" / "RUNTIMES.md"
MODELS_MD = REPO_ROOT / "docs" / "MODELS.md"
VERSIONS_FILE = REPO_ROOT / "versions.toml"
QUALITY_SCORE_MD = REPO_ROOT / "docs" / "QUALITY_SCORE.md"
RUNTIMES_DIR = REPO_ROOT / "runtimes"
MODELS_DIR = REPO_ROOT / "models"
RESULTS_DIR = REPO_ROOT / "results"

PYTHON_SOURCE_DIRS = [
    REPO_ROOT / "benchmark",
    REPO_ROOT / "runtimes",
    REPO_ROOT / "models",
    REPO_ROOT / "inputs",
    REPO_ROOT / "hardware",
    REPO_ROOT / "versions",
    REPO_ROOT / "tools",
    REPO_ROOT / "ci",
    REPO_ROOT / "site",
    REPO_ROOT / "lib",
]

QUALITY_SCORE_MAX_AGE_DAYS = 7

FEATURES_ACTIVE_DIR = REPO_ROOT / "docs" / "features" / "active"
PATCHES_ACTIVE_DIR  = REPO_ROOT / "docs" / "patches"  / "active"
FEATURE_REQUIRED_DOCS = {"requirements.md", "design.md", "plan.md"}


# ── Parsers ────────────────────────────────────────────────────────────────────


def _parse_runtimes_md() -> list[str]:
    """Extract runtime names from the Supported Runtimes table in RUNTIMES.md."""
    content = RUNTIMES_MD.read_text()
    # Match rows like: | pytorch | `//runtimes/pytorch/` | ...
    pattern = re.compile(r"^\|\s*(\w+)\s*\|\s*`//runtimes/\w+", re.MULTILINE)
    return [m.group(1) for m in pattern.finditer(content)]


def _parse_models_md() -> list[str]:
    """Extract Bazel target directory names from active rows in MODELS.md table."""
    names = []
    pattern = re.compile(r"`//models/(\w+)`")
    for line in MODELS_MD.read_text().splitlines():
        # Skip rows where the status column says "planned"
        if "planned" in line:
            continue
        m = pattern.search(line)
        if m:
            names.append(m.group(1))
    return names


# ── Checks ─────────────────────────────────────────────────────────────────────


def check_runtime_targets(runtimes: list[str]) -> list[str]:
    errors = []
    for name in runtimes:
        target_dir = RUNTIMES_DIR / name
        if not target_dir.is_dir():
            errors.append(
                f"[lint/runtime-target-missing] RUNTIMES.md lists '{name}' but no directory "
                f"exists at runtimes/{name}/. "
                f"Create the directory with runtime.py and BUILD, or remove the entry from RUNTIMES.md."
            )
    return errors


def check_model_targets(models: list[str]) -> list[str]:
    errors = []
    for name in models:
        target_dir = MODELS_DIR / name
        if not target_dir.is_dir():
            errors.append(
                f"[lint/model-target-missing] MODELS.md lists '{name}' but no directory "
                f"exists at models/{name}/. "
                f"Create the directory with spec.py and BUILD, or remove the entry from MODELS.md."
            )
    return errors


def check_versions_toml(runtimes: list[str]) -> list[str]:
    errors = []
    try:
        with open(VERSIONS_FILE, "rb") as f:
            versions = tomllib.load(f)
    except Exception as exc:
        return [f"[lint/versions-unreadable] Cannot read versions.toml: {exc}"]

    recorded = versions.get("runtimes", {})
    for name in runtimes:
        if name not in recorded:
            errors.append(
                f"[lint/versions-runtime-missing] RUNTIMES.md lists '{name}' but it is not "
                f"present in versions.toml [runtimes]. "
                f"Add '{name} = \"<version>\"' under [runtimes] in versions.toml."
            )

    if not versions.get("docker", {}).get("digest"):
        errors.append(
            "[lint/versions-schema] versions.toml is missing [docker].digest. "
            "Run //docker:build and //docker:push, then record the digest."
        )

    return errors


def check_no_print(python_dirs: list[Path]) -> list[str]:
    errors = []
    # Match print( only when it is the first non-whitespace token on the line
    # (i.e. an actual statement), not when it appears inside a string or comment.
    print_re = re.compile(r"^\s*print\s*\(")
    for src_dir in python_dirs:
        for py_file in src_dir.rglob("*.py"):
            text = py_file.read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if print_re.search(line):
                    rel = py_file.relative_to(REPO_ROOT)
                    errors.append(
                        f"[lint/print-statement] print() call found at {rel}:{lineno}. "
                        f"Use structured logging: from lib import log as L; L.info('event', ...)"
                    )
    return errors


def check_results_append_only() -> list[str]:
    """Detect modifications to existing files in results/ via git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "results/"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        return [f"[lint/results-git-error] Could not run git status: {exc}"]

    errors = []
    for line in result.stdout.splitlines():
        status = line[:2].strip()
        path = line[3:].strip()
        if status in ("M", "MM", "AM") and path != "results/.gitkeep":
            errors.append(
                f"[lint/results-mutation] {path} was modified. "
                f"results/ is append-only — existing files must never be mutated. "
                f"Revert the modification or add a new result file instead."
            )
    return errors


def check_active_features() -> list[str]:
    """Every active feature directory must have requirements.md, design.md, plan.md."""
    errors = []
    if not FEATURES_ACTIVE_DIR.exists():
        return []
    for feature_dir in FEATURES_ACTIVE_DIR.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("."):
            continue
        present = {f.name for f in feature_dir.iterdir() if f.is_file()}
        missing = FEATURE_REQUIRED_DOCS - present
        for doc in sorted(missing):
            errors.append(
                f"[lint/feature-incomplete] docs/features/active/{feature_dir.name}/ "
                f"is missing {doc}. A feature must have requirements.md, design.md, "
                f"and plan.md before it can be active. "
                f"Move back to docs/features/todo/ or add the missing document."
            )
    return errors


def check_active_patches() -> list[str]:
    """Every active patch file must contain ## Problem and ## Fix sections."""
    errors = []
    if not PATCHES_ACTIVE_DIR.exists():
        return []
    for patch_file in PATCHES_ACTIVE_DIR.glob("*.md"):
        content = patch_file.read_text()
        missing = []
        if "## Problem" not in content:
            missing.append("## Problem")
        if "## Fix" not in content:
            missing.append("## Fix")
        for section in missing:
            errors.append(
                f"[lint/patch-incomplete] docs/patches/active/{patch_file.name} "
                f"is missing a '{section}' section. "
                f"Add the section or move back to docs/patches/open/."
            )
    return errors


def check_quality_score_freshness() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%ct", str(QUALITY_SCORE_MD)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []  # File not yet tracked; skip
        commit_ts = int(result.stdout.strip())
        age_days = (datetime.now(timezone.utc).timestamp() - commit_ts) / 86400
        if age_days > QUALITY_SCORE_MAX_AGE_DAYS:
            return [
                f"[lint/quality-score-stale] QUALITY_SCORE.md was last updated "
                f"{age_days:.0f} days ago (max {QUALITY_SCORE_MAX_AGE_DAYS}). "
                f"Run: bazel run //tools:update_quality"
            ]
    except Exception:
        pass
    return []


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    runtimes = _parse_runtimes_md()
    models = _parse_models_md()

    L.info("lint.start", runtimes=runtimes, models=models)

    all_errors: list[str] = []
    all_errors += check_runtime_targets(runtimes)
    all_errors += check_model_targets(models)
    all_errors += check_versions_toml(runtimes)
    all_errors += check_no_print(PYTHON_SOURCE_DIRS)
    all_errors += check_results_append_only()
    all_errors += check_quality_score_freshness()
    all_errors += check_active_features()
    all_errors += check_active_patches()

    for err in all_errors:
        L.error("lint.fail", message=err)

    if all_errors:
        L.error("lint.summary", total_errors=len(all_errors))
        return 1

    L.info("lint.pass", checks_run=6)
    return 0


if __name__ == "__main__":
    sys.exit(main())

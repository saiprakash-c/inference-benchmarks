"""
//ci:doc_review

Semantic documentation reviewer. Uses Claude to detect drift between code and docs.

Two modes:
  CI mode   — PR_NUMBER env var set; posts findings as a PR comment via gh CLI
  Local mode — no PR_NUMBER; prints findings to stdout only

Usage (local):
  python ci/doc_review.py

Usage (CI):
  Invoked automatically by the agent-doc-review GitHub Actions job.

Exit codes:
  0 — pass (no errors, or API unavailable after retries)
  1 — fail (one or more error-severity findings)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent

# ── Tier-1: always included regardless of what changed ────────────────────────

TIER1_DOCS = [
    "ARCHITECTURE.md",
    "docs/design-docs/core-beliefs.md",
    "docs/design-docs/benchmark-methodology.md",
    "docs/OBSERVABILITY.md",
    "docs/VERSIONING.md",
    "docs/RUNTIMES.md",
    "docs/FEATURE_WORKFLOW.md",
]

# ── Tier-2: included when a file under the key prefix changes ─────────────────

TIER2_MAP = {
    "models/":            ["docs/MODELS.md"],
    ".github/workflows/": ["docs/CI.md"],
    "ci/":                ["docs/CI.md"],
    "site/":              ["docs/WEBSITE.md"],
    "docs/":              [],  # the doc is already in the diff itself
}

# Source file extensions that trigger doc checks when changed
SOURCE_EXTENSIONS = {".py", ".yml", ".yaml", ".sh", ".toml", ".dockerfile"}
SOURCE_FILENAMES  = {"Dockerfile", "BUILD"}

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
RETRY_BASE_SECS = 2


# ── Diff ───────────────────────────────────────────────────────────────────────


def get_pr_diff() -> str:
    """Return the full PR diff — everything this branch adds on top of main.

    Finds the merge-base between main and HEAD, then diffs from there to the
    working tree. This gives:
      - In CI (clean working tree): committed changes on the branch only
      - Locally: committed + staged + unstaged — the complete in-progress state

    Tries origin/main first (CI and normal local use), then main (local without
    a fetched remote ref).
    """
    for base in ("origin/main", "main"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", base],
            cwd=str(REPO_ROOT), capture_output=True,
        )
        if check.returncode != 0:
            continue

        merge_base = subprocess.run(
            ["git", "merge-base", base, "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if merge_base.returncode != 0:
            continue

        base_sha = merge_base.stdout.strip()
        result = subprocess.run(
            # Two-dot diff from merge-base to working tree:
            # in CI this equals origin/main...HEAD; locally it also
            # captures uncommitted (staged + unstaged) changes.
            ["git", "diff", base_sha],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    L.warn("doc_review.diff", reason="could not find a main branch ref to diff against")
    return ""


def changed_files(diff: str) -> list[str]:
    """Extract file paths from a unified diff."""
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


def is_source_file(path: str) -> bool:
    p = Path(path)
    return p.suffix.lower() in SOURCE_EXTENSIONS or p.name in SOURCE_FILENAMES


# ── Doc loading ────────────────────────────────────────────────────────────────


def load_doc(rel_path: str) -> str | None:
    full = REPO_ROOT / rel_path
    if full.exists():
        return full.read_text()
    return None


def get_tier1_docs() -> dict[str, str]:
    docs = {}
    for rel in TIER1_DOCS:
        content = load_doc(rel)
        if content:
            docs[rel] = content
    return docs


def get_tier2_docs(diff: str) -> dict[str, str]:
    files = changed_files(diff)
    to_load: set[str] = set()
    for f in files:
        for prefix, doc_list in TIER2_MAP.items():
            if f.startswith(prefix):
                to_load.update(doc_list)

    docs = {}
    for rel in to_load:
        content = load_doc(rel)
        if content:
            docs[rel] = content

    # For feature/patch files in the diff, load all .md files from that
    # specific feature directory or the patch file itself for full context.
    feature_dirs: set[Path] = set()
    for f in files:
        p = Path(f)
        # docs/features/<stage>/<name>/<file>.md → load the whole <name>/ dir
        if len(p.parts) >= 4 and p.parts[0] == "docs" and p.parts[1] == "features":
            feature_dir = REPO_ROOT / p.parts[0] / p.parts[1] / p.parts[2] / p.parts[3]
            if feature_dir.is_dir():
                feature_dirs.add(feature_dir)
        # docs/patches/<stage>/<name>.md → load the patch file itself
        elif len(p.parts) >= 4 and p.parts[0] == "docs" and p.parts[1] == "patches":
            patch_file = REPO_ROOT / f
            if patch_file.is_file():
                content = patch_file.read_text()
                docs[f] = content

    for feature_dir in feature_dirs:
        for md_file in sorted(feature_dir.glob("*.md")):
            rel = str(md_file.relative_to(REPO_ROOT))
            if rel not in docs:
                docs[rel] = md_file.read_text()

    return docs


# ── Prompt ────────────────────────────────────────────────────────────────────


SYSTEM_PROMPT = """\
You are a strict documentation reviewer for the inference-benchmarks repo.
Your job is to detect semantic drift: places where documentation no longer
accurately describes the code, or where code violates documented invariants.

You will be given:
1. Tier-1 invariant docs (always apply to every change)
2. Tier-2 component docs (relevant to the specific files changed)
3. The unified PR diff

Output ONLY valid JSON — no prose, no markdown fences — matching this schema:
{
  "status": "pass" | "fail",
  "findings": [
    {
      "file": "<doc or source file path>",
      "issue": "<what is wrong, one sentence>",
      "fix": "<what to change, one sentence>",
      "severity": "error" | "info"
    }
  ]
}

Rules:
- "error" severity means a factual inaccuracy or violated invariant → sets status to "fail"
- "info" severity means a style suggestion only → does not affect status
- If no findings, return {"status": "pass", "findings": []}
- Only report drift that is directly visible in the diff — do not speculate about
  code not shown
- Do not report errors on files in docs/features/todo/ or docs/patches/open/ — these are
  pre-design drafts, not invariants; they may be intentionally incomplete or inconsistent
  with the codebase until a design is approved and work begins

Feature/patch workflow checks (apply when docs/features/ or docs/patches/ files appear in the diff):
- A feature directory in active/ must have requirements.md, design.md, and plan.md
- A feature directory in completed/ must also have summary.md
- A feature's plan.md Status field must match its folder: todo→"awaiting approval",
  active→"approved" or "in progress", completed→"completed"
- If a plan.md step is implemented by code in the diff, the step should be marked
  complete in plan.md — flag if code is merged without the plan reflecting it
- If ALL steps in plan.md are marked complete (✅) in this diff, the feature folder
  must be moved to completed/ in the same PR — flag if it remains in active/
- If only SOME steps are complete, plan.md must be updated to mark exactly those
  steps ✅ so the doc reflects current progress — flag if completed steps are unmarked
- A patch file in active/ must contain both ## Problem and ## Fix sections
- A patch file in completed/ must have a Date completed field filled in
- If a feature folder moved from todo/ to active/ or active/ to completed/ in the
  diff, verify the move is consistent (all required docs present, status field updated)
"""


def build_prompt(diff: str, tier1: dict[str, str], tier2: dict[str, str]) -> str:
    parts = []

    parts.append("## Tier-1 invariant docs (always apply)\n")
    for path, content in tier1.items():
        parts.append(f"### {path}\n{content}\n")

    if tier2:
        parts.append("## Tier-2 component docs (relevant to this PR)\n")
        for path, content in tier2.items():
            parts.append(f"### {path}\n{content}\n")

    parts.append("## PR diff\n```diff\n" + diff + "\n```")

    return "\n".join(parts)


# ── Claude call ───────────────────────────────────────────────────────────────


def call_claude(user_message: str) -> dict | None:
    """Call Claude with retry. Returns parsed JSON or None on failure."""
    try:
        import anthropic
    except ImportError:
        L.error("doc_review.import", reason="anthropic package not installed — run: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        L.warn("doc_review.api_key", reason="ANTHROPIC_API_KEY not set — skipping review")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            L.info("doc_review.call", attempt=attempt, model=MODEL)
            message = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = message.content[0].text.strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            L.error("doc_review.parse", attempt=attempt, reason=str(exc), raw=raw[:200])
            return None
        except Exception as exc:
            L.warn("doc_review.retry", attempt=attempt, reason=str(exc))
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECS ** attempt)

    L.warn("doc_review.skip", reason=f"API unavailable after {MAX_RETRIES} attempts")
    return None


# ── Reporting ─────────────────────────────────────────────────────────────────


def format_comment(result: dict) -> str:
    status = result.get("status", "unknown")
    findings = result.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    infos  = [f for f in findings if f.get("severity") == "info"]

    if status == "pass":
        return "**Doc review: passed** — no drift detected between code and documentation."

    lines = ["**Doc review: failed** — the following documentation drift was detected:\n"]
    for f in errors:
        lines.append(f"- **`{f['file']}`**: {f['issue']}")
        lines.append(f"  - Fix: {f['fix']}")
    if infos:
        lines.append("\n**Suggestions (non-blocking):**")
        for f in infos:
            lines.append(f"- **`{f['file']}`**: {f['issue']}")
            lines.append(f"  - Suggestion: {f['fix']}")
    lines.append(
        "\nSelf-correct and push to re-run. "
        "See `docs/AGENT_LOOP.md §Self-correction protocol`."
    )
    return "\n".join(lines)


def post_pr_comment(body: str) -> None:
    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        return
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", body],
        cwd=str(REPO_ROOT),
    )


def report(result: dict | None, ci_mode: bool) -> int:
    if result is None:
        msg = "Doc review skipped — Anthropic API unavailable after retries."
        L.warn("doc_review.skip")
        if ci_mode:
            post_pr_comment(msg)
        else:
            L.warn("doc_review.output", message=msg)
        return 0

    findings = result.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    status = result.get("status", "pass")

    L.info("doc_review.result", status=status, total=len(findings), errors=len(errors))

    comment = format_comment(result)
    if ci_mode:
        post_pr_comment(comment)
    else:
        # Local mode: write human-readable output to stdout
        sys.stdout.write("\n" + comment + "\n\n")
        if findings:
            sys.stdout.write("--- raw findings ---\n")
            sys.stdout.write(json.dumps(findings, indent=2) + "\n")
        sys.stdout.flush()

    return 1 if errors else 0


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ci_mode = bool(os.environ.get("PR_NUMBER"))
    L.info("doc_review.start", ci_mode=ci_mode, model=MODEL)

    diff = get_pr_diff()
    if not diff:
        L.info("doc_review.nodiff", reason="no changes detected — skipping")
        return 0

    files = changed_files(diff)
    source_files = [f for f in files if is_source_file(f)]
    L.info("doc_review.scope", changed=len(files), source=len(source_files))

    tier1 = get_tier1_docs()
    tier2 = get_tier2_docs(diff)
    L.info("doc_review.docs", tier1=len(tier1), tier2=len(tier2))

    prompt = build_prompt(diff, tier1, tier2)
    result = call_claude(prompt)

    return report(result, ci_mode)


if __name__ == "__main__":
    sys.exit(main())

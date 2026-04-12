"""
//ci:weekly_doc_review

Weekly comprehensive documentation reviewer. Uses Claude to detect accumulated
drift between the full codebase and all documentation.

Two modes:
  CI mode   — WEEKLY_CI env var set; creates a GitHub Issue via gh CLI
  Local mode — no WEEKLY_CI; prints findings to stdout only

Usage (local):
  python ci/weekly_doc_review.py

Usage (CI):
  Invoked automatically by the weekly-doc-review GitHub Actions workflow.

Exit codes:
  0 — always exits 0 (issue creation is the artifact; this job must not block deploys)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import log as L  # noqa: E402

REPO_ROOT = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", Path(__file__).parent.parent))

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
RETRY_BASE_SECS = 2

# ── Source collection ─────────────────────────────────────────────────────────

# All docs under docs/ except docs/features/ and docs/patches/ (drafts in flux)
EXCLUDED_DOC_PREFIXES = ("docs/features/", "docs/patches/")

# Tier-1: root-level docs always included
ROOT_DOCS = ["ARCHITECTURE.md", "README.md"]

# Key source entry-point files
KEY_SOURCE_FILES = [
    "benchmark/runner.py",
    "benchmark/registry.py",
    "models/loader.py",
    "hardware/thor.py",
    "site/build.py",
    "site/deploy.py",
    "ci/doc_review.py",
    "versions/check.py",
]

# Runtime entry-points discovered dynamically
RUNTIME_PATTERN = "runtimes/*/runtime.py"

# Config files (header only to stay within context limits)
CONFIG_FILES = [
    "versions.toml",
    "pyproject.toml",
]
DOCKERFILE_PATH = "docker/Dockerfile"
DOCKERFILE_HEADER_LINES = 40


# ── File loading ──────────────────────────────────────────────────────────────


def load_file(rel_path: str, max_lines: int | None = None) -> str | None:
    full = REPO_ROOT / rel_path
    if not full.exists():
        return None
    text = full.read_text(encoding="utf-8", errors="replace")
    if max_lines is not None:
        lines = text.splitlines()
        text = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            text += f"\n... (truncated at {max_lines} lines)"
    return text


def collect_docs() -> dict[str, str]:
    """Return all .md files under docs/ except excluded prefixes, plus root docs."""
    docs: dict[str, str] = {}

    # Root-level docs
    for rel in ROOT_DOCS:
        content = load_file(rel)
        if content:
            docs[rel] = content

    # All docs under docs/ excluding features/ and patches/
    docs_dir = REPO_ROOT / "docs"
    if docs_dir.is_dir():
        for md_file in sorted(docs_dir.rglob("*.md")):
            rel = str(md_file.relative_to(REPO_ROOT))
            if any(rel.startswith(prefix) for prefix in EXCLUDED_DOC_PREFIXES):
                continue
            content = load_file(rel)
            if content:
                docs[rel] = content

    return docs


def collect_sources() -> dict[str, str]:
    """Return key source files and runtime entry-points."""
    sources: dict[str, str] = {}

    for rel in KEY_SOURCE_FILES:
        content = load_file(rel)
        if content:
            sources[rel] = content

    # Discover runtime entry-points
    for runtime_path in sorted(REPO_ROOT.glob(RUNTIME_PATTERN)):
        rel = str(runtime_path.relative_to(REPO_ROOT))
        content = load_file(rel)
        if content:
            sources[rel] = content

    return sources


def collect_configs() -> dict[str, str]:
    """Return config files, truncated to avoid overwhelming context."""
    configs: dict[str, str] = {}

    for rel in CONFIG_FILES:
        content = load_file(rel)
        if content:
            configs[rel] = content

    # Dockerfile header only
    content = load_file(DOCKERFILE_PATH, max_lines=DOCKERFILE_HEADER_LINES)
    if content:
        configs[DOCKERFILE_PATH] = content

    return configs


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a strict weekly documentation auditor for the inference-benchmarks repo.
Your job is to detect accumulated drift between the codebase and its documentation,
and to flag violations of the project's core beliefs.

You will be given:
1. All documentation files (docs/ tree, ARCHITECTURE.md, README.md)
2. Key source entry-point files (.py)
3. Config files (versions.toml, pyproject.toml, Dockerfile header)

Output ONLY valid JSON — no prose, no markdown fences — matching this schema exactly:
{
  "status": "pass" | "fail",
  "findings": [
    {
      "file": "<doc or source path>",
      "issue": "<what is wrong, one sentence>",
      "fix": "<what to change, one sentence>",
      "severity": "error" | "info",
      "fixable_by_agent": true | false
    }
  ]
}

Field semantics:
- "error" severity: a factual inaccuracy or violated invariant → sets status to "fail"
- "info" severity: a style suggestion or minor inconsistency → does not affect status
- fixable_by_agent: true  → the fix requires only editing a .md doc file; the agent
  may apply it without human involvement
- fixable_by_agent: false → the fix would require changing .py, .toml, .yml, Dockerfile,
  BUILD, or any non-doc file; OR the finding is a core-belief violation where the
  decision about whether to fix code or relax the belief belongs to the human.
  The agent MUST escalate these to the human before taking any action.

Core beliefs to enforce (from docs/design-docs/core-beliefs.md):
- Reproducibility: every result must be fully versioned (versions.toml, hw_id, timestamps)
- Legibility: no context lives outside the repo; docs are the system specification
- Boring Tech: prefer stable dependencies; no unexplained upgrades
- Agent-Agnostic: repo works with any agent via CLAUDE.md / AGENTS.md
- Entropy Management: drift is caught continuously, not in bursts; stale docs are a bug
- Enforce Invariants Not Implementations: architectural invariants (no cross-package imports,
  append-only results/, no print statements) enforced as Bazel lints
- Corrections Are Cheap; Waiting Is Expensive: agent self-correction is the default;
  human escalation is the exception

Critical rules:
- If a core-belief is violated by code (not docs), set fixable_by_agent: false — the
  human must decide whether to fix the code or update the belief. Never suggest
  silently correcting code to match docs.
- Only report concrete evidence of drift visible in the provided files — do not speculate
- If no issues are found, return {"status": "pass", "findings": []}
- Docs under docs/features/ and docs/patches/ are excluded — do not review them
"""


def build_prompt(
    docs: dict[str, str],
    sources: dict[str, str],
    configs: dict[str, str],
) -> str:
    parts: list[str] = []

    parts.append("## Documentation files\n")
    for path, content in docs.items():
        parts.append(f"### {path}\n{content}\n")

    if sources:
        parts.append("## Key source files\n")
        for path, content in sources.items():
            parts.append(f"### {path}\n{content}\n")

    if configs:
        parts.append("## Config files\n")
        for path, content in configs.items():
            parts.append(f"### {path}\n{content}\n")

    return "\n".join(parts)


# ── Claude call ───────────────────────────────────────────────────────────────


def call_claude(user_message: str) -> dict | None:
    """Call Claude with retry. Returns parsed JSON dict or None on failure."""
    try:
        import anthropic
    except ImportError:
        L.error("weekly_doc_review.import", reason="anthropic package not installed — run: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        L.warn("weekly_doc_review.api_key", reason="ANTHROPIC_API_KEY not set — skipping review")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    raw = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            L.info("weekly_doc_review.call", attempt=attempt, model=MODEL)
            message = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = message.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                raw = raw.rsplit("```", 1)[0].strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            L.error("weekly_doc_review.parse", attempt=attempt, reason=str(exc), raw=raw[:200])
            return None
        except Exception as exc:
            L.warn("weekly_doc_review.retry", attempt=attempt, reason=str(exc))
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECS ** attempt)

    L.warn("weekly_doc_review.skip", reason=f"API unavailable after {MAX_RETRIES} attempts")
    return None


# ── Reporting ─────────────────────────────────────────────────────────────────


def format_issue_body(result: dict, run_date: str) -> str:
    """Format findings as a GitHub Issue body (markdown)."""
    findings = result.get("findings", [])
    agent_fixable = [f for f in findings if f.get("fixable_by_agent") and f.get("severity") == "error"]
    escalations = [f for f in findings if not f.get("fixable_by_agent") and f.get("severity") == "error"]
    infos = [f for f in findings if f.get("severity") == "info"]

    lines = [f"# Weekly doc review — {run_date}\n"]

    if not findings:
        lines.append("**All clear.** No drift detected between code and documentation.")
        return "\n".join(lines)

    if agent_fixable:
        lines.append("## Doc fixes (agent can apply)\n")
        lines.append("| File | Issue | Fix |")
        lines.append("|---|---|---|")
        for f in agent_fixable:
            file_col = f.get("file", "")
            issue_col = f.get("issue", "").replace("|", "\\|")
            fix_col = f.get("fix", "").replace("|", "\\|")
            lines.append(f"| `{file_col}` | {issue_col} | {fix_col} |")
        lines.append("")

    if escalations:
        lines.append("## Escalations (human decision required)\n")
        lines.append(
            "> These findings involve code violating core beliefs or require changes "
            "outside of doc files. **Do not auto-fix.** A human must decide the correct action.\n"
        )
        lines.append("| File | Issue | Fix |")
        lines.append("|---|---|---|")
        for f in escalations:
            file_col = f.get("file", "")
            issue_col = f.get("issue", "").replace("|", "\\|")
            fix_col = f.get("fix", "").replace("|", "\\|")
            lines.append(f"| `{file_col}` | {issue_col} | {fix_col} |")
        lines.append("")

    if infos:
        lines.append("## Suggestions (non-blocking)\n")
        lines.append("| File | Issue | Suggestion |")
        lines.append("|---|---|---|")
        for f in infos:
            file_col = f.get("file", "")
            issue_col = f.get("issue", "").replace("|", "\\|")
            fix_col = f.get("fix", "").replace("|", "\\|")
            fixable = f.get("fixable_by_agent", True)
            marker = "" if fixable else " *(escalate)*"
            lines.append(f"| `{file_col}` | {issue_col} | {fix_col}{marker} |")
        lines.append("")

    return "\n".join(lines)


def format_local_output(result: dict) -> str:
    """Format findings for stdout in local mode."""
    findings = result.get("findings", [])
    status = result.get("status", "pass")

    if status == "pass":
        return "**Weekly doc review: passed** — no drift detected."

    agent_fixable = [f for f in findings if f.get("fixable_by_agent") and f.get("severity") == "error"]
    escalations = [f for f in findings if not f.get("fixable_by_agent") and f.get("severity") == "error"]
    infos = [f for f in findings if f.get("severity") == "info"]

    lines = ["**Weekly doc review: findings detected**\n"]

    if agent_fixable:
        lines.append("### Doc fixes (agent can apply):\n")
        for f in agent_fixable:
            lines.append(f"- **`{f['file']}`**: {f['issue']}")
            lines.append(f"  - Fix: {f['fix']}")
        lines.append("")

    if escalations:
        lines.append("### Escalations (human decision required):\n")
        for f in escalations:
            lines.append(f"- **`{f['file']}`**: {f['issue']}")
            lines.append(f"  - Required decision: {f['fix']}")
        lines.append("")

    if infos:
        lines.append("### Suggestions (non-blocking):\n")
        for f in infos:
            marker = "" if f.get("fixable_by_agent", True) else " *(escalate)*"
            lines.append(f"- **`{f['file']}`**: {f['issue']}{marker}")
            lines.append(f"  - Suggestion: {f['fix']}")

    return "\n".join(lines)


def create_github_issue(title: str, body: str) -> None:
    """Create a GitHub Issue with the doc-drift label via gh CLI."""
    result = subprocess.run(
        [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", "doc-drift",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        L.warn(
            "weekly_doc_review.issue_create",
            reason="gh issue create failed",
            stderr=result.stderr.strip(),
        )
    else:
        L.info("weekly_doc_review.issue_created", url=result.stdout.strip())


def report(result: dict | None, ci_mode: bool, run_date: str) -> int:
    if result is None:
        msg = "Weekly doc review skipped — Anthropic API unavailable after retries."
        L.warn("weekly_doc_review.skip")
        if ci_mode:
            create_github_issue(
                title=f"doc review: {run_date}",
                body=msg,
            )
        else:
            sys.stdout.write("\n" + msg + "\n\n")
            sys.stdout.flush()
        return 0  # never fail — issue is the artifact

    findings = result.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    status = result.get("status", "pass")

    L.info(
        "weekly_doc_review.result",
        status=status,
        total=len(findings),
        errors=len(errors),
        agent_fixable=sum(1 for f in errors if f.get("fixable_by_agent")),
        escalations=sum(1 for f in errors if not f.get("fixable_by_agent")),
    )

    if ci_mode:
        body = format_issue_body(result, run_date)
        if findings:
            create_github_issue(title=f"doc review: {run_date}", body=body)
        else:
            L.info("weekly_doc_review.clean", reason="no findings — skipping issue creation")
    else:
        output = format_local_output(result)
        sys.stdout.write("\n" + output + "\n\n")
        if findings:
            sys.stdout.write("--- raw findings (JSON) ---\n")
            sys.stdout.write(json.dumps(findings, indent=2) + "\n")
        sys.stdout.flush()

    return 0  # always exit 0 per spec


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    from datetime import date

    run_date = os.environ.get("REVIEW_DATE", date.today().isoformat())
    ci_mode = bool(os.environ.get("WEEKLY_CI"))

    L.info("weekly_doc_review.start", ci_mode=ci_mode, model=MODEL, run_date=run_date)

    docs = collect_docs()
    sources = collect_sources()
    configs = collect_configs()

    L.info(
        "weekly_doc_review.scope",
        docs=len(docs),
        sources=len(sources),
        configs=len(configs),
    )

    prompt = build_prompt(docs, sources, configs)
    result = call_claude(prompt)

    return report(result, ci_mode, run_date)


if __name__ == "__main__":
    sys.exit(main())

# Plan: weekly-doc-reviewer

Status: awaiting approval

---

## Requirements from User

- Run a comprehensive doc review weekly (GitHub Actions cron)
- Also runnable locally inside dev/rt Docker containers
- Produce structured output an agent can use to fix docs directly
- Agent auto-fixes docs only; code-vs-core-beliefs violations are escalated to human for
decision before any action is taken

## Updates on User Requirements

None. Requirements are clear and achievable.

## Design

### Two new files

```
ci/weekly_doc_review.py          ← review script (CI + local)
.github/workflows/weekly-doc-review.yml  ← cron schedule
```

No new packages required; reuses anthropic SDK already present.

### How it differs from ci/doc_review.py


| Dimension     | doc_review.py (PR)         | weekly_doc_review.py          |
| ------------- | -------------------------- | ----------------------------- |
| Scope         | Git diff only              | Full codebase snapshot        |
| Trigger       | Every PR push              | Weekly cron + manual dispatch |
| Output target | PR comment via gh CLI      | GitHub Issue via gh CLI       |
| Finding type  | Drift introduced by PR     | Accumulated drift anywhere    |
| Agent action  | Human reads, self-corrects | Agent auto-applies doc fixes  |


### Source collection strategy

Too much content → Claude context limit. Collect selectively:

1. **All docs** — every `.md` under `docs/` (excluding `docs/features/` and `docs/patches/`), plus `ARCHITECTURE.md`, `README.md`
2. **Key source files** — the entry-point `.py` of each top-level package:
  `benchmark/runner.py`, `benchmark/registry.py`, `models/loader.py`,
   `runtimes/*/runtime.py`, `hardware/thor.py`, `site/build.py`,
   `site/deploy.py`, `ci/doc_review.py`, `versions/check.py`
3. **Config files** — `versions.toml`, `pyproject.toml`, `docker/Dockerfile` header

### Output schema (superset of doc_review.py)

```json
{
  "status": "pass" | "fail",
  "findings": [
    {
      "file": "<doc path>",
      "issue": "<one-sentence description>",
      "fix": "<one-sentence prescription>",
      "severity": "error" | "info",
      "fixable_by_agent": true | false
    }
  ]
}
```

`fixable_by_agent: true`  → doc is wrong, agent edits the markdown  
`fixable_by_agent: false` → code violates a core-belief; agent MUST escalate to human

### CI mode (GitHub Actions)

- Creates a GitHub Issue titled `"doc review: YYYY-MM-DD"` with label `doc-drift`
- Issue body: markdown table of findings, split into two sections:
  - "Doc fixes (agent can apply)" — errors the agent can self-correct
  - "Escalations (human decision required)" — core-belief violations
- Exit 0 even if findings exist (issue creation is the artifact; CI should not block deploys)

### Local mode

- Prints the same markdown to stdout (no issue created)
- Agent reads stdout, applies doc fixes, prints escalations

### GitHub Actions schedule

```yaml
on:
  schedule:
    - cron: '0 6 * * 0'   # Every Sunday at 06:00 UTC
  workflow_dispatch:        # Manual trigger
```

Permissions: `contents: read`, `issues: write`

### Agent safety rule (enforced in prompt, not code)

The prompt explicitly instructs Claude:

- Findings that require changing `.py`, `.toml`, `.yml`, or any non-doc file →
`fixable_by_agent: false`, severity `error`
- Claude must never suggest code changes as the fix for a core-beliefs violation —
it must describe what the human needs to decide

## Tasks

- Write `ci/weekly_doc_review.py` with local + CI modes
- Write `.github/workflows/weekly-doc-review.yml`
- Move feature folder from `todo/` → `active/`
- Test locally: `bazel run //ci:weekly_doc_review`
- Open PR, verify CI passes

## Updates on Approved Plan

*(append here after approval — never modify sections above)*
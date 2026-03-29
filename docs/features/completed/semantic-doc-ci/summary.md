# Summary: semantic-doc-ci
Completed: 2026-03-29

## What was built

An LLM-powered CI check (`ci/doc_review.py`) that detects semantic drift
between code and documentation on every PR. The check:

- Runs as a GitHub Actions job (`agent-doc-review`) gated behind mechanical lint
- Is a hard merge blocker (exit 1 on any `severity: error` finding)
- Posts findings as a PR comment with actionable fix instructions
- Also runs locally (no `PR_NUMBER` → stdout mode) for pre-PR self-correction
- Uses `claude-sonnet-4-6` at `temperature=0` with 3-retry exponential backoff;
  fail-open (exit 0) if the API is unavailable

Two-tier context strategy:
- **Tier-1:** invariant docs always included (ARCHITECTURE.md, core-beliefs.md,
  benchmark-methodology.md, OBSERVABILITY.md, VERSIONING.md, RUNTIMES.md,
  FEATURE_WORKFLOW.md)
- **Tier-2:** component docs loaded from the diff — models/, ci/, site/,
  .github/workflows/, and dynamically: all .md files from any feature directory
  or patch file that appears in the diff

The system prompt enforces feature/patch workflow state: todo→active→completed
transitions, plan.md status consistency, summary.md presence in completed/,
and patch ## Problem + ## Fix section requirements.

## Deviations from plan

- `docs/FEATURE_WORKFLOW.md` added to Tier-1 (not in original design) — needed
  to give the reviewer the workflow rules it checks against
- `get_tier2_docs()` extended with dynamic feature/patch directory loading
  (not in original design) — required to support workflow-state checking
- The system prompt's blanket exclusion of docs/features/ and docs/patches/
  was replaced with explicit workflow-state rules

## Lessons learned

- The doc reviewer will flag its own feature docs if they drift from the
  implementation — use this as a forcing function to keep plan.md current
- `temperature=0` is essential; the same prompt gave different results at
  default temperature, making the check non-deterministic
- `git diff <merge-base>` (not `origin/main...HEAD`) is the right local diff
  command — the three-dot form stops at the last commit and misses uncommitted
  working-tree changes
- The print() lint regex must be anchored (`^\s*print\s*\(`) to avoid false
  positives in docstrings and error message strings

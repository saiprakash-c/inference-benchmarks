# Design: semantic-doc-ci
Status: approved

## Approach

Use the Claude API to review every PR for semantic drift between code and
documentation. The check runs as a GitHub Actions job (`Agent doc review`) on
every PR, is a hard merge blocker, and posts findings as a PR comment with
actionable instructions. The script also runs locally so the agent can
self-correct before opening a PR.

### What gets checked

Two directions of drift:

| Changed file type | What to verify |
|---|---|
| Any source file changed (`.py`, `.yml`, `Dockerfile`, `BUILD`, `.toml`, `.sh`) | All `.md` files that describe that file/component are still accurate |
| `.md` file changed | All code references, class names, function signatures, and file paths cited in the doc still exist and match |
| Any source file | Inline comments and docstrings in changed hunks are consistent with the surrounding code |

### Scope strategy: diff-first, not full-repo

On every PR, the reviewer sees:

1. The full unified diff (`git diff origin/main...HEAD`)
2. Tier-1 docs (always included — define invariants every PR must respect)
3. Tier-2 docs (diff-scoped — component docs inferred from changed file paths)

Full-repo scan is reserved for the weekly `//ci:doc_gardening` job.

### Tier-1 docs (always included)

```python
TIER1_DOCS = [
    "ARCHITECTURE.md",
    "docs/design-docs/core-beliefs.md",
    "docs/design-docs/benchmark-methodology.md",
    "docs/OBSERVABILITY.md",
    "docs/VERSIONING.md",
    "docs/RUNTIMES.md",
]
```

### Tier-2 docs (diff-scoped)

```python
TIER2_MAP = {
    "models/":            ["docs/MODELS.md"],
    ".github/workflows/": ["docs/CI.md"],
    "ci/":                ["docs/CI.md"],
    "site/":              ["docs/WEBSITE.md"],
    "docs/":              [],  # doc itself is already in the diff
}
```

### LLM integration

- **Model:** `claude-sonnet-4-6`
- **Auth:** `ANTHROPIC_API_KEY` GitHub Actions secret; locally via `.env`
- **SDK:** `anthropic` Python package
- **Prompt structure:**
  1. System: role, output format, drift definition
  2. User: Tier-1 docs + Tier-2 docs + PR diff
  3. Request: structured JSON findings

### Two modes: CI and local

| Mode | Triggered when | Output |
|---|---|---|
| **CI** | `PR_NUMBER` env var set | Posts findings as PR comment via `gh pr comment`; exits 1 on fail |
| **Local** | No `PR_NUMBER` | Prints findings to stdout only; same exit codes |

Agent workflow: run locally before `gh pr create`, self-correct, then open PR.

### Output format

```json
{
  "status": "pass" | "fail",
  "findings": [
    {
      "file": "docs/RUNTIMES.md",
      "issue": "Documents pytorch runtime as implementing `preprocess()` but runtime.py has no such method",
      "fix": "Remove the `preprocess()` row from the interface table in RUNTIMES.md",
      "severity": "error" | "info"
    }
  ]
}
```

- `error` severity → `status: fail`
- `info` severity → style suggestion only, does not affect status

### Pass / fail criteria

- `pass` — no findings, or all findings are `severity: info`
- `fail` — any `severity: error` finding (factual inaccuracy or violated invariant)

### Self-correction loop

**In CI:** agent reads PR comment findings, applies fixes, pushes. Check re-runs.
After two failed attempts, escalate to human.

**Locally:** agent runs `python ci/doc_review.py` before opening a PR, reads
stdout findings, applies fixes, re-runs until clean.

---

## Components affected

- `ci/doc_review.py` — new script, the reviewer
- `ci/BUILD` — add `doc_review` py_binary
- `.github/workflows/pr.yml` — add `agent-doc-review` job
- `requirements.in` / `requirements.txt` — add `anthropic`
- `docs/CI.md` — add `ANTHROPIC_API_KEY` to secrets table
- `.env.example` — add `ANTHROPIC_API_KEY` (variable name only, never the value)

---

## Tradeoffs considered

**Diff-scoped vs full-repo on every PR**
Full-repo is thorough but expensive and slow. Diff-scoped keeps cost and latency
low and findings directly relevant to the PR. Full-repo is for `//ci:doc_gardening`.

**Sonnet vs Opus**
Sonnet is the right call here — lower cost, fast enough for CI, and the tiered
context structure (Tier-1 invariants always present) compensates for the reduced
reasoning depth. Opus reserved for weekly gardening if needed.

**PR comment vs check annotation**
Annotations require exact line numbers, which the LLM can't reliably produce.
PR comments are always accurate and the agent reads them via `gh pr view --comments`.

**Fail-open on API errors**
If the API is down, the check warns and exits 0 (does not block the PR).
3 retries with exponential backoff before declaring skip.

**ANTHROPIC_API_KEY in .env.example**
Safe — `.env.example` documents the variable *name* with a placeholder value.
The actual key lives in `.env` (gitignored) locally and as a GitHub Actions
secret in CI. No credentials are ever committed.

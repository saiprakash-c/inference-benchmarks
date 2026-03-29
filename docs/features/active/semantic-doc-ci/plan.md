# Plan: semantic-doc-ci
Status: in progress

## Steps

1. ✅ Add `anthropic` to `requirements.in` and regenerate `requirements.txt`
2. ✅ Create `ci/doc_review.py` — the reviewer script (CI + local modes)
3. ✅ Add `doc_review` py_binary to `ci/BUILD`
4. ✅ Add `agent-doc-review` job to `.github/workflows/pr.yml`
5. ✅ Add `ANTHROPIC_API_KEY` to `.env.example` and `docs/CI.md` secrets table
6. ✅ Move feature folder to `docs/features/active/semantic-doc-ci/`
7. Open PR, verify the check runs and passes on itself

## Files to create / modify

- `requirements.in` — add `anthropic`
- `requirements.txt` — regenerate (pip-compile)
- `ci/doc_review.py` — new script (main deliverable)
- `ci/BUILD` — add `doc_review` py_binary
- `.github/workflows/pr.yml` — add `agent-doc-review` job
- `.env.example` — add `ANTHROPIC_API_KEY` (variable name + placeholder only)
- `docs/CI.md` — add `ANTHROPIC_API_KEY` row to secrets table

## `ci/doc_review.py` structure

```
main()
  1. get_pr_diff()             — git diff origin/main...HEAD
  2. get_tier1_docs()          — hardcoded list, always loaded
  3. get_tier2_docs(diff)      — inferred from changed file paths via TIER2_MAP
  4. build_prompt(diff, docs)  — system + user message
  5. call_claude(prompt)       — anthropic SDK, claude-sonnet-4-6, 3 retries
  6. parse_response(raw)       — extract structured JSON findings
  7. report(findings)          — CI mode: gh pr comment; local mode: stdout
  8. exit 0 (pass) or 1 (fail)
```

Tier-1 and Tier-2 constants per design.md.

## API retry policy

On any Anthropic API error (network, rate-limit, 5xx):
- Retry up to 3 times with exponential backoff (2s, 4s, 8s)
- After 3 failures: log warning, post "doc review skipped (API unavailable)"
  comment in CI mode, exit 0 (fail-open)

## Workflow job

```yaml
agent-doc-review:
  name: Agent doc review
  runs-on: ubuntu-latest
  permissions:
    contents: read
    pull-requests: write
  needs: [lint]           # only run if mechanical lint passes first
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install -r requirements.txt
    - run: python ci/doc_review.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        PR_NUMBER: ${{ github.event.pull_request.number }}
```

## Local usage (pre-PR self-correction)

```bash
# From repo root, with ANTHROPIC_API_KEY set in .env or shell
python ci/doc_review.py
# Prints findings to stdout, exits 0 (pass) or 1 (fail)
# Fix findings, re-run, then open PR when clean
```

## Test / validation

- Add `ANTHROPIC_API_KEY` secret to the GitHub repo before merging
- The PR for this feature is the first real test — check should run and pass
- To verify detection: introduce a deliberate drift in a scratch branch
  (e.g. rename a method in a runtime stub without updating RUNTIMES.md)
  and confirm the check catches and reports it

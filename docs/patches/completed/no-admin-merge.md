# Patch: no-admin-merge
Type: chore
Date opened: 2026-03-29
Date completed: 2026-03-29

## Problem
`gh pr merge --admin` was used to bypass branch protection when GitHub
reported "not mergeable" despite all checks being green. This defeats the
purpose of branch protection rules.

## Root cause
When GitHub checks pass but the merge API still returns "not mergeable",
it is a brief propagation delay — not a real failure. The correct response
is to wait and retry, not to escalate to --admin.

## Fix
- Add explicit prohibition of `--admin` to `CLAUDE.md` and `docs/CI.md`
- Document the 15–30s wait-and-retry pattern for propagation delays
- Never use --admin without explicit human approval

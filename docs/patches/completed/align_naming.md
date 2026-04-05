# Patch: align_naming
Type: chore
Date opened: 2026-04-04
Date completed: 2026-04-04

## Problem
`docs/patches/` used `open/` for unstarted patches while `docs/features/` used `todo/`. Inconsistent naming added cognitive overhead.

## Fix
Renamed `docs/patches/open/` → `docs/patches/todo/`. Updated all references in CONTEXT.md, FEATURE_WORKFLOW.md, AGENT_LOOP.md, ci/lint.py, and ci/doc_review.py.

## Lessons learned
None — mechanical rename.

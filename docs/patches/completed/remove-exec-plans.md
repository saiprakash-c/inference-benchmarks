# Patch: remove-exec-plans
Type: chore
Date opened: 2026-03-29
Date completed: 2026-04-04

## Problem
`docs/exec-plans/` existed in the repo but was not part of the active workflow.
It was referenced in `CLAUDE.md` and `ci/doc_review.py` but added cognitive
overhead without providing value — features and patches already cover planning
and decision history.

## Fix
- Deleted `docs/exec-plans/` and all contents (via `git rm -r`)
- Removed references from CONTEXT.md (and by symlink, CLAUDE.md)
- Removed exec-plans exclusion line from `ci/doc_review.py` system prompt
- Removed "Exec-plan hygiene" check from `docs/agents/evaluator.md`
- Cleaned up parenthetical reference in `docs/features/completed/three-agent-feature-workflow/requirements.md`

## Lessons
Decision history is better captured in patch/feature summaries and git log
than in a dedicated exec-plans tree.

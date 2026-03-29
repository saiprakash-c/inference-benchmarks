# Patch: remove-exec-plans
Type: chore
Date opened: 2026-03-29

## Problem
`docs/exec-plans/` exists in the repo but is not part of the active workflow.
It is referenced in `CLAUDE.md` and `docs/CI.md` (doc_review exclusion) but
adds cognitive overhead without providing value — features and patches already
cover planning and decision history.

## Fix
- Delete `docs/exec-plans/` and all contents
- Remove references to it from `CLAUDE.md`, `docs/CI.md`, and any other docs
- Update the doc_review system prompt exclusion to drop the exec-plans carve-out

Date completed: 2026-03-29

## Lessons learned

The exec-plans directory was referenced in more places than the patch description listed:
CONTEXT.md map section, docs/WEBSITE.md hosting-decision paragraph, ci/doc_review.py
system prompt carve-out, and docstrings in all four runtime stubs. A broad grep for
"exec-plans" before committing confirmed all references were cleared. The doc_review
system prompt carve-out was removed so the reviewer now covers all active docs uniformly.

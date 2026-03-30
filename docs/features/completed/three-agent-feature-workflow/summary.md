# Summary: three-agent-feature-workflow
Completed: 2026-03-29

## What was built

A three-role feature pipeline orchestrated by the main agent (Claude Code itself):

- **`.claude/commands/feature.md`** — `/feature` skill with three entry points
  (`/feature <name>`, `/feature plan <name>`, `/feature code <name>`). Handles
  stage detection from filesystem state, `BEFORE_SHA` capture before each Coder
  launch, git diff display in terminal, Coder↔Evaluator loop with 3-strike
  escalation, and folder moves on approval and merge.
- **`docs/agents/coder.md`** — Versioned system prompt for the Coder agent;
  first-run and re-launch protocols; hard constraints (no PR, no touching locked
  docs, no Co-Authored-By).
- **`docs/agents/evaluator.md`** — Versioned system prompt for the Evaluator
  agent; five checks; structured `evaluation_coder.md` output format with YAML
  front matter failure counters; clean-pass self-deletion protocol.
- **`ci/lint.py`** — New `check_no_evaluation_file_committed()` check; errors if
  `evaluation_coder.md` is found committed under `docs/features/`.
- **`.gitignore`** — `docs/features/**/evaluation_coder.md` exclusion.
- **`docs/AGENT_LOOP.md`**, **`docs/FEATURE_WORKFLOW.md`**, **`docs/CI.md`** —
  Updated feature track to reflect three-role pipeline; patch track untouched.

## Deviations from plan

- None. All 9 plan steps executed as specified (steps 1–8 are file changes; step 9 is a lint validation run with no file artifact).

## Lessons learned

- The Evaluator caught a single doc-accuracy issue (diagram attributed `summary.md`
  to "main agent" while prose and all other docs said "Coder agent"). The
  Coder↔Evaluator loop resolved it in one iteration without human involvement.
- Keeping the Evaluator's checklist concrete (cite file + section for each
  requirement) made findings unambiguous and easy for Coder to address on re-launch.
- `BEFORE_SHA=$(git rev-parse HEAD)` before each Coder launch is the right
  approach for isolating exactly what the Coder committed; avoids showing
  pre-existing staged changes in the diff.

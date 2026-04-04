# Summary: simple-feature-workflow
Completed: 2026-04-04

## What was built

Simplified the feature workflow from 3 docs (requirements + design + plan) with 2 approval gates to 2 docs (requirements + plan) with 1 approval gate. `plan.md` now has five fixed sections that subsume design: Requirements from User, Updates on User Requirements, Design, Tasks, Updates on Approved Plan.

Updated: `docs/FEATURE_WORKFLOW.md`, `ci/lint.py`, `ci/doc_review.py`, `docs/agents/coder.md`, `docs/agents/evaluator.md`.

## Deviations from plan

None.

## Lessons learned

- The coder.md constraint for `plan.md` needed nuance: "never modify" is still correct but the `## Updates on Approved Plan` section is explicitly append-only, so clarifying that distinction in the table is useful.

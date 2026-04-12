# QUALITY_SCORE

Component grades, update trigger, and ownership.

## Grading Schema

Each component is graded on three criteria:

| Criterion | Weight | Description |
|---|---|---|
| Test coverage % | 40% | Line coverage of Python targets under //benchmark and //tools |
| Doc freshness | 30% | Days since last //ci:lint passed without error |
| Lint pass rate | 30% | Fraction of //ci:lint runs passing over last 7 cron runs |

Overall grade = weighted average, expressed as A/B/C/D/F.

## Components

| Component | Owner | Grade | Last Updated | Notes |
|---|---|---|---|---|
| benchmark harness | unassigned | — | 2026-04-12 | pre-implementation |
| version checker | unassigned | — | 2026-04-12 | pre-implementation |
| site builder | unassigned | — | 2026-04-12 | pre-implementation |
| CI jobs | unassigned | — | 2026-04-12 | pre-implementation |
| documentation coverage | unassigned | — | 2026-04-12 | pre-implementation |

## Update Trigger

- **Automatic:** `//ci:doc_gardening` updates this table on weekly cron (Mondays 08:00 UTC)
- **Manual:** `//tools:update_quality` triggers an immediate update on demand
- QUALITY_SCORE.md must be updated within the last 7 days or //ci:lint
  will flag it as stale

## Grade Criteria Detail

**A:** ≥90% test coverage, doc freshness ≤2 days, lint pass rate ≥95%
**B:** ≥75% coverage, freshness ≤5 days, lint rate ≥85%
**C:** ≥60% coverage, freshness ≤7 days, lint rate ≥70%
**D:** ≥40% coverage, freshness ≤14 days, lint rate ≥50%
**F:** Below D thresholds, or any mandatory field in result schema not covered by tests

## Ownership

Component owners are responsible for:
- Keeping grade at B or above
- Responding to doc_gardening PRs within one agent session
- Updating this table when ownership changes

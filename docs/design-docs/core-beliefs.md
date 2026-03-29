# Core Beliefs

Guiding principles for the inference-benchmarks project. Every design
decision should be traceable to one of these.

## Reproducibility
Every run is fully versioned and re-runnable. versions.toml is committed
with each run and contains exact software versions, hardware ID, and
timestamps. A result without full version metadata is not a result.

## Legibility
Any agent session must understand the full system from the repo alone.
No context lives outside the repo. Documentation is not optional
annotation — it is the system specification.

## Boring Tech
Prefer stable, well-documented dependencies over clever ones. The goal
is benchmark correctness, not infrastructure novelty. Upgrade reluctantly
and with clear justification.

## Agent-Agnostic
The repo works with any agent (human or AI) via the CONTEXT.md symlinks.
CLAUDE.md and AGENTS.md are identical pointers to CONTEXT.md so any
agent framework picks up orientation automatically.

## Entropy Management
Drift between code and docs is caught continuously via //ci:lint,
not in painful bursts. Weekly //ci:doc_gardening keeps debt visible.
Stale docs are a bug, not a backlog item.

## Enforce Invariants, Not Implementations
Constrain boundaries; allow freedom within them. Architectural invariants
(no cross-package imports, append-only results/, no print statements) are
enforced as Bazel lints — not prose. If an invariant is not mechanically
checked, it does not exist.

## Corrections Are Cheap; Waiting Is Expensive
Merge early, merge often. Correctness gates are the only hard blockers.
Test flakes trigger a follow-up run, never a merge block. Agent self-
correction is the default; human escalation is the exception.

# inference-benchmarks

Goal: benchmark inference runtimes on Nvidia embedded GPUs, publish
daily to a static website.

## Map
ARCHITECTURE.md     — pipeline overview and Bazel target map
TASKS.md            — current work items
versions.toml       — runtime version state (committed each run)

## Work tracking
docs/FEATURE_WORKFLOW.md               — how features and patches are managed
docs/features/todo/                    — features awaiting design/plan approval
docs/features/active/                  — features approved and in progress
docs/features/completed/               — shipped features with summaries
docs/patches/open/                     — open bug fixes and small changes
docs/patches/active/                   — patches in progress
docs/patches/completed/                — completed patches with lessons

## Docs
docs/design-docs/core-beliefs.md       — principles and philosophy
docs/design-docs/benchmark-methodology.md — how results are collected
docs/exec-plans/active/                — current execution plans
docs/exec-plans/completed/             — decision history
docs/exec-plans/tech-debt-tracker.md  — known debt, prioritized

## Specs
docs/RUNTIMES.md      — pluggability contract, how to add a runtime
docs/MODELS.md        — supported models, input shapes, precisions
docs/VERSIONING.md    — versions.toml schema and update rules
docs/OBSERVABILITY.md — structured log format, anomaly thresholds
docs/AGENT_LOOP.md    — agent execution loop and escalation criteria
docs/CI.md            — cron schedule, PR lifecycle, merge philosophy
docs/WEBSITE.md       — results → static site pipeline

## Key Bazel targets
//benchmark:run, //versions:check, //tools:validate_results,
//site:build, //site:deploy, //ci:lint, //ci:doc_gardening,
//docker:build, //docker:push, //tools:ssh_run

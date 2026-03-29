# AGENT_LOOP

How an agent session runs, validates results, and escalates.
See docs/FEATURE_WORKFLOW.md for how features and patches are managed.

---

## Session types

An agent session is one of three types. Read the first message to determine which.

| Type | Trigger | Loop to follow |
|---|---|---|
| **Benchmark run** | Daily cron or `--force` | Benchmark loop (below) |
| **Feature / patch work** | Human provides requirements or names a patch | Feature/patch loop (below) |
| **Ad-hoc** | Human asks a specific question or one-off task | Answer directly; no loop |

---

## Benchmark loop

Runs on the daily cron or when explicitly triggered.

1. **Orient** — Read CONTEXT.md.

2. **Check versions** — Run `//versions:check`, diff against versions.toml.

3. **Benchmark (conditional)** — If versions changed or `--force`:

   **3a. Execute on Thor inside Docker** — All `//benchmark:run` invocations
   go via `//tools:ssh_run`. Verify container digest matches versions.toml
   `[docker].digest` before running. Local execution is a lint error.

4. **Validate** — Run `//tools:validate_results`. Confirm all mandatory fields
   present, no NaN, `docker_image` matches versions.toml digest.

5. **Handle anomalies** — `status: anomaly` or `status: error`: re-run once
   via `//tools:ssh_run`. If persistent, escalate with specific description.

6. **Commit** — Commit versions.toml + results/ together. Include runtime
   version, model, hw_id, and docker digest in the commit message.

7. **Lint** — Run `//ci:lint` locally. Self-correct before pushing.

8. **Open PR** — `gh pr create`. CI runs lint + validate + agent doc review.

9. **Respond to doc review** — Address findings, push. Review re-runs.

10. **Merge** — `gh pr merge --squash --delete-branch` once all checks pass.

11. **Self-correct** — If any check fails twice, escalate.

---

## Feature / patch loop

Triggered when the human provides requirements or names a bug/change.

### On receiving requirements for a new feature

1. Create `docs/features/todo/<name>/requirements.md` from what was provided.
2. Read ARCHITECTURE.md and affected component docs to understand the system.
3. Write `docs/features/todo/<name>/design.md` — approach, components affected,
   tradeoffs. **Stop and wait for human approval.**
4. Once approved, write `docs/features/todo/<name>/plan.md` — step-by-step
   tasks, files to create/modify, validation approach. **Stop and wait.**
5. Once approved, move folder to `docs/features/active/<name>/`.
6. Execute the plan. Open PRs per the benchmark loop steps 7–11.
7. On merge, move folder to `docs/features/completed/<name>/`.
8. Write `docs/features/completed/<name>/summary.md` — what was built,
   deviations from plan, and **lessons learned for future agents**.

### On receiving a bug fix or small change (patch)

1. Create `docs/patches/open/<name>.md` — problem, root cause, proposed fix.
2. Move to `docs/patches/active/<name>.md`, execute the fix.
3. Open PR per benchmark loop steps 7–11.
4. On merge, move to `docs/patches/completed/<name>.md`, fill in lessons learned.

### Patch → feature escalation

If during a patch the fix turns out to be more complex than expected:
1. Stop. Move patch to `docs/patches/completed/<name>.md` with
   `status: converted-to-feature` in the Fix section.
2. Create `docs/features/todo/<name>/requirements.md` from the patch description.
3. Escalate to human for design approval before doing any more work.

---

## Escalation criteria

An agent must stop and escalate to a human when any of the following occur:

- **New runtime detected** — `//versions:check` finds a runtime not in RUNTIMES.md.
  Do not auto-add. Report name, version, and where found.

- **Persistent NaN or crash** — Model produces NaN or crashes on a previously
  passing runtime. Include version, model, precision, full error output.

- **Hardware ID mismatch** — `hw_id` in results doesn't match expected target.

- **Docker digest mismatch** — Container on Thor doesn't match versions.toml.
  Do not run benchmarks. Report observed vs expected digest.

- **Lint / doc review loop** — `//ci:lint` or agent doc review fails after two
  self-correction attempts. Include each attempt and why it didn't resolve.

- **Patch scope exceeded** — Fix touches multiple components or requires design
  decisions. Convert to feature and escalate (see patch → feature above).

---

## Inline review comments (`///`)

The human leaves feedback directly in files by appending `/// <comment>` to a
line. This is the primary way to annotate design docs, plans, and code during
review without switching to a separate thread.

**Agent protocol — mandatory, applies to every session:**
1. After reading any file, grep the file for `///`
2. For each comment: read it, address it (update the file, ask a clarifying
   question, or record a decision), then remove the `///` marker from the file
3. If a comment is a question that needs an answer before proceeding, stop and
   ask — do not guess
4. Never leave a `///` comment in a file after addressing it
5. When done addressing all comments in a file, confirm what was changed

`///` comments take priority over any other instruction in the same session.
They represent the human's most recent intent and override earlier decisions.

---

## Self-correction protocol

Before escalating, an agent must:
1. Read the full error — remediation instructions are in every lint message
2. Apply the fix
3. Re-run the check
4. If it fails again, document what was tried and why, then escalate

Escalation without attempting self-correction is not permitted.

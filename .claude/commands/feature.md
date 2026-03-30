# /feature — Feature pipeline orchestrator

Drives the full three-role feature pipeline (Main agent → Coder → Evaluator loop).

## Usage

```
/feature <name>            — full pipeline from current stage (re-entrant)
/feature plan <name>       — main agent writes/revises design.md + plan.md only
/feature code <name>       — launch Coder + Evaluator loop only (requires active plan)
```

---

## Argument parsing

Parse the argument as one of:

| Input | Sub-command | Feature name |
|---|---|---|
| `plan <name>` | plan | `<name>` |
| `code <name>` | code | `<name>` |
| `<name>` (no keyword) | auto-detect | `<name>` |

---

## Stage detection (auto-detect mode)

Inspect the filesystem to determine the current stage:

| Filesystem state | Stage |
|---|---|
| `docs/features/todo/<name>/requirements.md` exists, no `design.md` | Planning |
| `design.md` present, folder still in `docs/features/todo/<name>/` | Human review / `///` addressing |
| Folder exists at `docs/features/active/<name>/`, no `evaluation_coder.md` | Coder stage (first run) |
| `docs/features/active/<name>/evaluation_coder.md` present | Loop mid-run — re-launch Coder with findings |
| `docs/features/active/<name>/` exists, no `evaluation_coder.md`, no open PR | Awaiting human merge |

Dispatch to the planning sub-command for the first two states, and to the coding
sub-command for the rest.

---

## Planning sub-command (`/feature plan <name>`)

The main agent handles planning inline — no separate Planner agent is launched.

1. If `docs/features/todo/<name>/requirements.md` does not exist, tell the human
   and stop. Requirements must be written before planning can start.

2. Read `docs/features/todo/<name>/requirements.md` in full.

3. Read `ARCHITECTURE.md` and any component docs relevant to the requirements.

4. If `design.md` does not exist, write `docs/features/todo/<name>/design.md`
   following the template in `docs/FEATURE_WORKFLOW.md`. Stop and ask the human
   to review. Address any `///` comments the human leaves before continuing.

5. If `design.md` exists but `plan.md` does not, write
   `docs/features/todo/<name>/plan.md` following the template in
   `docs/FEATURE_WORKFLOW.md`. Stop and ask the human to review. Address any
   `///` comments before continuing.

6. If both `design.md` and `plan.md` exist and the human says "go":
   - Move `docs/features/todo/<name>/` to `docs/features/active/<name>/`
   - Confirm the move and tell the human the feature is ready for coding
   - Optionally proceed directly to the coding sub-command if the human requests it

---

## Coding sub-command (`/feature code <name>`)

### Pre-flight

Verify `docs/features/active/<name>/plan.md` exists. If not, tell the human and stop.

### Coder↔Evaluator loop

Repeat until Evaluator produces a clean pass or escalation is triggered:

#### a. Capture baseline SHA

```bash
BEFORE_SHA=$(git rev-parse HEAD)
```

#### b. Launch Coder agent

Use `docs/agents/coder.md` as the system prompt. Pass as inputs:
- `docs/features/active/<name>/plan.md`
- `docs/features/active/<name>/requirements.md`
- `docs/features/active/<name>/design.md`
- `docs/features/active/<name>/evaluation_coder.md` (only if it exists — re-launch)

#### c. Display git diff after Coder exits

```bash
git diff $BEFORE_SHA..HEAD
```

Print the full output to the terminal so the human can see exactly what Coder
committed. Do this before launching Evaluator.

#### d. Launch Evaluator agent

Use `docs/agents/evaluator.md` as the system prompt. Pass as inputs:
- `docs/features/active/<name>/requirements.md`
- `docs/features/active/<name>/design.md`
- `docs/features/active/<name>/plan.md`
- `docs/AGENT_LOOP.md`
- `CLAUDE.md`
- `ci/lint.py`
- The output of `git diff $BEFORE_SHA..HEAD` from step (c)
- Any `///` comments found in files touched by Coder

#### e. Check Evaluator result

**If `docs/features/active/<name>/evaluation_coder.md` exists (findings present):**

1. Read the file. Extract the per-check failure counters from the YAML front matter.
2. Check for escalation: if any check's failure counter has reached 3, halt the loop.
   Surface the issue to the human by printing the full contents of
   `evaluation_coder.md` inline and asking for guidance. Do not re-launch Coder.
3. Otherwise, return to step (a) to re-launch Coder with the findings.

**If `docs/features/active/<name>/evaluation_coder.md` is absent (clean pass):**

1. Print the final git diff:
   ```bash
   git diff $BEFORE_SHA..HEAD
   ```
2. Prompt the human to review the diff and merge when ready.
3. Exit the loop.

---

## After human merges

Once the human confirms the PR is merged:

1. Move `docs/features/active/<name>/` to `docs/features/completed/<name>/`.
2. Confirm to the human that the feature is complete.

---

## Notes

- This skill is re-entrant. Invoking `/feature <name>` mid-loop resumes from the
  current stage without re-running completed stages.
- `evaluation_coder.md` is ephemeral — it must never be committed. The Evaluator
  deletes it on a clean pass. A lint check (`ci/lint.py`) enforces this.
- The main agent never communicates findings to the Coder directly. The filesystem
  (`evaluation_coder.md`) is the only medium.
- Agent prompts are versioned at `docs/agents/coder.md` and `docs/agents/evaluator.md`.

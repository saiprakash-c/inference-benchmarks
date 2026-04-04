# Requirements: three-agent-feature-workflow

Date: 2026-03-29
Status: completed

## Goal

Replace the single-agent feature loop with a lean three-role pipeline —
Main agent, Coder, and Evaluator — where the main agent (Claude Code itself)
orchestrates the whole flow without being a separate launched agent.

## Background

The original design had five agent launches per iteration (Planner, two
Evaluator passes, Coder, Evaluator again) plus loops. Each launch is expensive:
the agent rebuilds context from scratch on every cold start. The simplified
design cuts launched agents to two (Coder and Evaluator), with the main
agent handling planning, orchestration, and loop control directly.

## Pipeline overview

```
Main agent writes design.md + plan.md
        │
        ▼
Human reviews (/// protocol) — main agent addresses comments
        │
        ▼
Human says "go" — folder moves to active/
        │
        ▼
Main agent launches Coder agent
        │
        ▼
Coder finishes — main agent runs git diff and displays it in the terminal
        │
        ▼
Main agent launches Evaluator agent
        │
        ├─ findings? ──► main agent passes evaluation_coder.md to Coder (new launch)
        │                Coder addresses findings, pushes
        │                Main agent shows updated git diff in terminal
        │                Main agent re-launches Evaluator ──► loop
        │
        └─ no issues ──► evaluation_coder.md deleted
                              └──► main agent prompts human to merge
```

PR is never opened until Evaluator finds no issues.

## Agent roles

### Main agent (Claude Code — not a launched agent)

- Writes `design.md` and `plan.md` directly (no separate Planner agent)
- Handles `///` review protocol with the human
- Moves folder from `todo/` to `active/` on human approval
- Launches Coder agent
- After Coder finishes: runs `git diff` and displays the full diff in the terminal
- Launches Evaluator agent
- Reads `evaluation_coder.md`; if findings exist, re-launches Coder with the
  evaluation file as additional context (does not kill Coder mid-run)
- Re-launches Evaluator after each Coder revision
- On clean Evaluator pass: deletes `evaluation_coder.md`, prompts human to review
  git diff and merge
- Escalates to human if the same check fails three consecutive times

### Coder agent (launched)

- Input: `docs/features/active/<name>/plan.md`, `requirements.md`, `design.md`
  for context; `evaluation_coder.md` if this is a re-launch after findings
- Executes every step in `plan.md` in order (or addresses findings on re-launch)
- Does not modify `requirements.md`, `design.md`, or `plan.md`
- Does not open a PR — that is the main agent's job after Evaluator passes
- Writes `summary.md` only on the final pass (after Evaluator is satisfied)

### Evaluator agent (launched)

- Input: `requirements.md`, `design.md`, `plan.md`, `AGENT_LOOP.md`, `CLAUDE.md`,
  lint rules, the implementation diff, any open `///` comments in touched files
- Checks:
  1. Every requirement in `requirements.md` is addressed in the implementation
  2. Every plan step is reflected in the diff
  3. No repo conventions are violated (commit trailers, merge flags, doc accuracy)
  4. No unanswered `///` comments remain in any file touched by Coder
  5. `summary.md` is present, complete, and accurate
- Writes `evaluation_coder.md` with pass/fail per check and a findings section
- On clean pass: deletes `evaluation_coder.md` itself
- Reports findings to main agent — does not communicate with Coder directly
- Does not modify any code or planning docs

## Git diff display

After every Coder run (initial and re-launches), the main agent must:
1. Run `git diff` (or `git diff HEAD` against the feature branch base) and
   print the full output to the terminal before launching Evaluator
2. After a clean Evaluator pass, print the final diff again before prompting
   human to merge — so the human sees exactly what is going into the PR

## Triggering the pipeline

```
/feature <name>          — full pipeline from current stage (re-entrant)
/feature plan <name>     — main agent writes/revises design.md + plan.md only
/feature code <name>     — launch Coder + Evaluator loop only (requires active plan)
```

The main agent determines current stage from filesystem state:
- `todo/<name>/requirements.md` exists, no `design.md` → start planning
- `design.md` present, in `todo/` → resume after human review / `///` addressing
- Folder in `active/` → Coder + Evaluator stage
- `evaluation_coder.md` present → loop is mid-run; re-launch Coder with findings

## Agent prompt/config location

```
docs/agents/
  coder.md       — system prompt + input/output contract for Coder
  evaluator.md   — system prompt + checklist template for Evaluator
```

No `planner.md` — main agent handles planning directly.

## Requirements

- Main agent (Claude Code) handles all planning; no Planner agent is launched
- Main agent must display `git diff` output in the terminal after every Coder run
- Evaluator is a hard gate: PR is not opened until Evaluator finds no issues
- `evaluation_coder.md` is ephemeral — deleted on clean pass, never committed
- On re-launch after findings, Coder receives `evaluation_coder.md` as input;
  it is not killed mid-run
- Coder must not touch `requirements.md`, `design.md`, or `plan.md`
- Evaluator reports to main agent; does not communicate with Coder directly
- If the same check fails three consecutive times, main agent escalates to human
- Agents share no context between launches; filesystem is the only medium
- Pipeline is re-entrant: any stage can be re-triggered without re-running earlier ones
- Agent prompts live in `docs/agents/` and are versioned

## Out of scope

- Separate Planner agent (main agent handles this)
- Evaluator grading the plan/design docs (only grades code)
- Parallelism between Coder and Evaluator
- Automated merge (always requires human sign-off)
- Evaluator auto-fixing findings

## Open questions

- None.

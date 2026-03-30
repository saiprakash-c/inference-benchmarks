# Design: three-agent-feature-workflow

Status: awaiting approval

## Approach

The main agent (Claude Code itself) handles planning and orchestration inline —
no separate Planner agent is launched. Only two agent types are ever launched:
Coder and Evaluator. This minimises cold-start cost while preserving the
quality gate that motivated the original design.

The `/feature` skill encodes the orchestration logic. The main agent reads
filesystem state to determine the current stage, launches the appropriate
sub-agent, and drives the Coder↔Evaluator loop until Evaluator finds no issues.
After every Coder run the main agent prints the full `git diff` in the terminal
so the human always knows what is on the branch.

### Stage detection

The skill resolves the current stage by inspecting the filesystem:

| Filesystem state | Stage |
|---|---|
| `todo/<name>/requirements.md` exists, no `design.md` | Planning |
| `design.md` present, folder still in `todo/` | Human review / `///` addressing |
| Folder in `active/`, no `evaluation_coder.md` | Coder stage (first run) |
| `evaluation_coder.md` present in `active/<name>/` | Loop mid-run — re-launch Coder |
| No evaluation file, no open PR | Awaiting human merge |

### Planning (main agent, inline)

The main agent writes `design.md` and `plan.md` directly — identical to the
current single-agent flow in `AGENT_LOOP.md`. The `///` review protocol is
unchanged. No agent is launched for this phase.

### Coder agent

A launched sub-agent with a single, narrow contract:
- **Input on first run:** `plan.md`, `requirements.md`, `design.md`
- **Input on re-launch:** same, plus `evaluation_coder.md` (findings to address)
- **Output:** committed code changes; `summary.md` written on final pass only

The Coder does not open a PR. It does not touch `requirements.md`, `design.md`,
or `plan.md`.

### Evaluator agent

A launched sub-agent that grades the implementation and reports to the main
agent. It never communicates with Coder directly.

**Checks:**
1. Every requirement in `requirements.md` is addressed
2. Every plan step is reflected in the diff
3. No repo conventions violated (commit trailers, merge flags, doc accuracy)
4. No unanswered `///` comments in files touched by Coder
5. `summary.md` present, complete, and accurate

Evaluator writes `evaluation_coder.md` with pass/fail per check. On clean pass
it deletes the file itself before exiting.

### Coder↔Evaluator loop

```
Main agent launches Coder
        │
        ▼
Main agent runs git diff → prints to terminal
        │
        ▼
Main agent launches Evaluator
        │
        ├─ evaluation_coder.md present (findings)
        │        │
        │        ▼
        │   main agent re-launches Coder with evaluation_coder.md as input
        │   Coder addresses findings
        │   main agent runs git diff → prints to terminal
        │   main agent re-launches Evaluator ──────────────────┐
        │                                                      │ loop
        └─ evaluation_coder.md absent (clean pass) ◄──────────┘
                │
                ▼
        main agent prints final git diff
        main agent prompts human to review and merge
```

**Escalation:** if the same numbered check fails three times consecutively,
the main agent halts the loop and surfaces the issue to the human with the
last `evaluation_coder.md` content inline.

### Git diff display

Before each Coder launch, the main agent captures the current HEAD SHA. After
Coder exits, it runs:

```
git diff $BEFORE_SHA..HEAD
```

This shows exactly the commits Coder made in that session — pre-existing
staged or unstaged changes are excluded. The diff is printed to the terminal
before Evaluator is launched, and again on final clean pass before prompting
the human to merge.

### Re-entrancy

Every sub-command is idempotent. The skill reads filesystem state first and
skips completed stages. `/feature <name>` re-invoked mid-loop resumes from
the current stage without re-running earlier ones.

### Ephemeral evaluation file

`evaluation_coder.md` must never be committed. Deleted by Evaluator on clean
pass. Lint check added to catch accidental commits. Never present in
`completed/`.

---

## Components affected

- `docs/agents/coder.md` — new file; Coder system prompt and I/O contract
- `docs/agents/evaluator.md` — new file; Evaluator system prompt and checklist
- `.claude/commands/feature.md` — new file; `/feature` skill that orchestrates
  the pipeline
- `docs/AGENT_LOOP.md` — update **feature sub-section only** (§"On receiving
  requirements for a new feature"); replace steps 1–8 with a condensed pointer
  to `/feature` and `docs/agents/`; patch sub-section is untouched
- `docs/FEATURE_WORKFLOW.md` — update **§Stage progression, feature track only**;
  reflect that main agent writes design/plan, Evaluator gate precedes human
  review of code; patch track is untouched
- `ci/lint.py` — add one check: `evaluation_coder.md` must not be committed
- `docs/CI.md` — add `feature/<name>` branch-naming pattern
- `.gitignore` — add `evaluation_coder.md` exclusion under `docs/features/`

---

## Tradeoffs considered

### No separate Planner agent
Main agent plans inline. Eliminates one cold-start, keeps the human's review
loop identical to today. Downside: planning is not independently auditable via
a versioned prompt. Acceptable because the main agent's behaviour is governed
by `AGENT_LOOP.md` and `FEATURE_WORKFLOW.md`, which are already versioned.

### Coder re-launched (not continued) on findings
Each Coder run is a fresh agent with `evaluation_coder.md` as extra input.
Alternative was to pass findings as a message to a running Coder session, but
sub-agents are stateless by design here. Re-launching keeps the contract clean
and avoids accumulated context drift across iterations.

### Single evaluation file vs. per-phase files
Previous design had `evaluation_planner.md` and `evaluation_coder.md`. With no
Planner phase evaluation, only `evaluation_coder.md` remains. Simpler.

### Evaluator reports to main agent, not Coder
Keeps Coder's contract narrow (code only). Main agent decides whether to loop
or escalate, which gives the human a natural intervention point.

---

## Open questions

- None.

# Plan: three-agent-feature-workflow

Status: awaiting approval

## Steps

1. **Create `docs/agents/coder.md`**
  System prompt and I/O contract for the Coder agent. Must specify:
  - On first run: read `plan.md`, `requirements.md`, `design.md`; execute
  every plan step in order; do not modify `requirements.md`, `design.md`,
  or `plan.md`; do not open a PR; write `summary.md` only after Evaluator
  signals clean pass (i.e., when `evaluation_coder.md` is absent)
  - On re-launch: read `evaluation_coder.md` in addition to the above; address
  every failing check; do not re-do work that already passed
  - Grep all touched files for `///` comments and address them
  - Commit changes with a message matching repo conventions (no Co-Authored-By)
2. **Create `docs/agents/evaluator.md`**
  System prompt and checklist for the Evaluator agent. Must specify:
  - Inputs: `requirements.md`, `design.md`, `plan.md`, `AGENT_LOOP.md`,
  `CLAUDE.md`, lint rules, `git diff <base>...HEAD`, any `///` comments
  in touched files
  - Run all five checks (requirements coverage, plan step coverage, repo
  conventions, `///` comments, `summary.md` completeness)
  - Output format: `evaluation_coder.md` with YAML front matter
  (`phase: coder`, `run: N`, per-check `failures` counter), then a
  `## Results` table (pass/fail per check), then `## Findings` (one
  subsection per failing check with actionable description)
  - On clean pass: write the file with empty Findings, then delete it and exit
  - Do not modify any code or planning docs
3. **Create `.claude/commands/feature.md` (the `/feature` skill)**
  The orchestrating skill. Must:
  - Parse argument as `[plan|code] <name>` or `<name>`
  - Detect current stage from filesystem (see design.md §Stage detection)
  - **Planning sub-command (`/feature plan <name>` or full pipeline start):**
  Main agent writes/revises `design.md` and `plan.md` inline; prompts human
  for `///` review; addresses all comments; waits for human "go"; moves
  folder from `todo/<name>/` to `active/<name>/`
  - **Coding sub-command (`/feature code <name>` or pipeline continuation):**
  a. Verify `active/<name>/plan.md` exists
  b. Launch Coder agent (`docs/agents/coder.md`), passing:
    - `active/<name>/plan.md`, `requirements.md`, `design.md` as inputs
    - `evaluation_coder.md` as additional input if it exists (re-launch)
    c. Before launching Coder: capture `BEFORE_SHA=$(git rev-parse HEAD)`
       After Coder exits: run `git diff $BEFORE_SHA..HEAD` and print to
       terminal — shows only commits made by Coder in this session, ignoring
       any pre-existing staged or unstaged changes
    d. Launch Evaluator agent (`docs/agents/evaluator.md`)
    e. If `evaluation_coder.md` exists (findings): read failure counters; if
       any check has failed 3× consecutively, halt and surface to human with
       evaluation content inline; else go to step (b)
    f. If `evaluation_coder.md` absent (clean pass): print final git diff to
       terminal; prompt human to review and merge
  - **Full pipeline `/feature <name>`:** detect stage and dispatch to planning
  or coding sub-command as appropriate
4. **Update `docs/AGENT_LOOP.md` — feature sub-section only**
  Replace the current "On receiving requirements for a new feature" steps 1–8
   with a condensed description:
  - Main agent writes `design.md` and `plan.md` directly
  - Human reviews via `///` protocol; main agent addresses all comments
  - Human approves; main agent runs `/feature <name>` to launch Coder +
  Evaluator loop
  - Coder implements; main agent displays git diff after each Coder run
  - Evaluator gates the PR; main agent loops until clean pass
  - Human merges
   Retain the patch sub-section, `///` protocol section, and all other
   content exactly as-is.
5. **Update `docs/FEATURE_WORKFLOW.md` — §Stage progression, feature track only**
  Update the stage progression diagram and prose to reflect:
  - `design.md` and `plan.md` are written by the **main agent** (not a
  launched agent)
  - Coder↔Evaluator loop gates the PR
  - `evaluation_coder.md` is ephemeral; never committed
  - `summary.md` written by Coder after clean Evaluator pass, before PR
   Do not touch the patch track or document templates section.
6. **Update `ci/lint.py` — one new check**
   `check_no_evaluation_file_committed()`: scan `docs/features/active/` and
   `docs/features/todo/` for `evaluation_coder.md`. If found, emit:
   `[lint/evaluation-file-committed] docs/features/active/<name>/evaluation_coder.md`
   `must not be committed. Delete it before committing.`
   Wire into `main()`.
7. **Update `docs/CI.md` — branch naming**
  Add `feature/<name>` to the branch-naming table with description:
   "PRs opened by the Coder agent for feature implementations."
8. **Update `.gitignore`**
  Add `evaluation_coder.md` exclusion under `docs/features/`:
   If a broader `evaluation_*.md` pattern already covers it, skip.
9. **Run `//ci:lint` locally**
  `bazel run //ci:lint` must exit 0. The new evaluation-file check must pass
   (no `evaluation_coder.md` files exist). All pre-existing checks must still
   pass.

---

## Files to create / modify

- `docs/agents/coder.md` — create
- `docs/agents/evaluator.md` — create
- `.claude/commands/feature.md` — create
- `docs/AGENT_LOOP.md` — modify (feature sub-section only)
- `docs/FEATURE_WORKFLOW.md` — modify (stage progression, feature track only)
- `ci/lint.py` — modify (two new checks)
- `docs/CI.md` — modify (branch naming table)
- `.gitignore` — modify (evaluation_coder.md exclusion)

---

## Test / validation

- After step 3: manually invoke `/feature plan <name>` on a scratch feature;
confirm main agent writes design/plan, prompts for review, moves folder on
"go"
- After step 3: invoke `/feature code <name>`; confirm Coder launches, git diff
prints after it finishes, Evaluator launches, and `evaluation_coder.md`
appears if there are findings
- After step 6: create a dummy `evaluation_coder.md` in
`docs/features/active/test/`, run `//ci:lint`, confirm lint error fires;
delete the file, confirm it passes
- After step 9: `bazel run //ci:lint` exits 0 on the full diff before PR


# FEATURE WORKFLOW

Two tracks for all work: **features** (design-first, approval-gated) and
**patches** (describe-and-do, no approvals needed). Every piece of work
lives in one of these two tracks — nothing is worked on outside them.

---

## Track 1: Features

For any change that requires design thinking, touches multiple components,
or has architectural impact.

### Directory structure

```
docs/features/
  todo/<name>/           ← requirements + design + plan accumulate here
    requirements.md      ← always created first, from user requirements
    design.md            ← created by agent, awaits human approval
    plan.md              ← created by agent after design approved, awaits approval
  active/<name>/         ← folder moved here once plan is approved
    requirements.md
    design.md
    plan.md
  completed/<name>/      ← folder moved here once work is merged
    requirements.md
    design.md
    plan.md
    summary.md           ← written by agent on completion
```

### Stage progression

```
[requirements captured]
        │
        ▼
  todo/<name>/requirements.md
        │  agent writes design.md
        ▼
  todo/<name>/design.md        ← HUMAN APPROVAL REQUIRED
        │  agent writes plan.md
        ▼
  todo/<name>/plan.md          ← HUMAN APPROVAL REQUIRED
        │  human says "go"
        ▼
  active/<name>/               ← folder moved, work begins
        │  work merged to main
        ▼
  completed/<name>/            ← folder moved, agent writes summary.md
```

### Document templates

**`requirements.md`**
```markdown
# Requirements: <name>
Date: YYYY-MM-DD
Status: todo

## Goal
One sentence.

## Requirements
- ...

## Out of scope
- ...

## Open questions
- ...
```

**`design.md`**
```markdown
# Design: <name>
Status: awaiting approval

## Approach
...

## Components affected
- component/ — what changes

## Tradeoffs considered
...

## Open questions
- ...
```

**`plan.md`**
```markdown
# Plan: <name>
Status: awaiting approval

## Steps
1. ...
2. ...

## Files to create / modify
- path/to/file.py — what changes

## Test / validation
...
```

**`summary.md`**
```markdown
# Summary: <name>
Completed: YYYY-MM-DD

## What was built
...

## Deviations from plan
...

## Lessons learned
(for future agents and humans)
- ...
```

---

## Track 2: Patches

For isolated bug fixes and small changes where the root cause and fix
are already known. No design doc. No approval gates.

### Directory structure

```
docs/patches/
  open/<name>.md       ← patch described, not yet started
  active/<name>.md     ← being worked on (file moved)
  completed/<name>.md  ← done (file moved)
```

A patch is a **single file** that moves between `open/`, `active/`,
and `completed/` as work progresses.

### Patch file template

```markdown
# Patch: <name>
Type: bug | chore | refactor
Date opened: YYYY-MM-DD
Date completed: (on completion)

## Problem
What is broken or needs changing, and where.

## Root cause
Why it is happening (if a bug).

## Fix
What was / will be changed.

## Lessons learned
(on completion — anything surprising or worth noting for future agents)
```

### When a patch becomes a feature

If during a patch an agent discovers the fix is more complex than expected
(touches multiple components, requires design decisions), it must:
1. Stop work on the patch
2. Move the patch file to `docs/patches/completed/<name>.md` with
   status `converted-to-feature` in the Fix section
3. Create `docs/features/todo/<name>/requirements.md` derived from
   the patch description
4. Escalate to human for design approval before proceeding

---

## Lint enforcement (`//ci:lint`)

- Every directory in `docs/features/active/` must contain
  `requirements.md`, `design.md`, and `plan.md` — missing any of these
  is a lint error.
- Every file in `docs/patches/active/` must contain a `## Problem`
  and a `## Fix` section — missing either is a lint error.

Error format:
```
[lint/feature-incomplete]: docs/features/active/my_feature/ is missing
plan.md. A feature must have requirements.md, design.md, and plan.md
before it can be active. Move back to todo/ or add the missing document.

[lint/patch-incomplete]: docs/patches/active/my_fix.md is missing
## Fix section. Add the section or move back to open/.
```

---

## Deciding which track to use

| Signal | Track |
|---|---|
| You already know the fix | Patch |
| Fix touches one file or one function | Patch |
| Fix requires no design decisions | Patch |
| Change touches multiple components | Feature |
| Change requires architecture decisions | Feature |
| You need to think about how to approach it | Feature |
| Mid-patch you discover it's more complex | Convert to feature |

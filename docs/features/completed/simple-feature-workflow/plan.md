# Plan: simple-feature-workflow
Status: completed

---

## Requirements from User

- Agent must not touch `requirements.md` — human-only
- Merge `design.md` + `plan.md` into a single `plan.md`
- `plan.md` sections (fixed): Requirements from User · Updates on User Requirements · Design · Tasks · Updates on Approved Plan
- Updates on User Requirements: agent rationalises any additions/subtractions to the human's requirements
- Design must be mostly visual; minimal prose
- Tasks must be a checklist
- `plan.md` must be concise for quick review
- Agent writes `plan.md`, asks human for review, then on approval moves folder to `active/` and works through the checklist, appending to Updates on Approved Plan for any in-flight deviations

---

## Updates on User Requirements

None. Requirements are unambiguous and fully implementable as stated.

---

## Design

### Old workflow (3 docs, 2 approvals)

```
requirements.md ──► design.md ──[approval]──► plan.md ──[approval]──► active/
  (human)          (agent)                   (agent)
```

### New workflow (2 docs, 1 approval)

```
requirements.md ──► plan.md ──[approval]──► active/
  (human)          (agent)
```

### plan.md anatomy

```
┌─────────────────────────────────┐
│ ## Requirements from User       │  ← copied/summarised from requirements.md
│ ## Updates on User Requirements │  ← agent additions/subtractions + rationale
│ ## Design                       │  ← visual-first; minimal prose
│ ## Tasks                        │  ← [ ] checklist; agent ticks as it goes
│ ## Updates on Approved Plan     │  ← append-only; never touches approved content
└─────────────────────────────────┘
```

### Files touched

```
docs/FEATURE_WORKFLOW.md       — rewrite feature track section
ci/lint.py                     — FEATURE_REQUIRED_DOCS: drop "design.md"
ci/doc_review.py               — system prompt: drop design.md from required set
docs/agents/coder.md           — drop design.md from inputs + constraints
docs/agents/evaluator.md       — drop design.md from inputs + constraints
```

---

## Tasks

- [x] Update `docs/FEATURE_WORKFLOW.md`: new directory structure, stage progression, templates, lint section
- [x] Update `ci/lint.py`: `FEATURE_REQUIRED_DOCS = {"requirements.md", "plan.md"}`; update error message
- [x] Update `ci/doc_review.py` system prompt: active feature requires `requirements.md` and `plan.md` only
- [x] Update `docs/agents/coder.md`: remove `design.md` from inputs table, execution protocol, and hard constraints
- [x] Update `docs/agents/evaluator.md`: remove `design.md` from inputs table and hard constraints

---

## Updates on Approved Plan

_(append here after approval — do not modify above)_

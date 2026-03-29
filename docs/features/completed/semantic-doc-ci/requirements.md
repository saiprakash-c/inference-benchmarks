# Requirements: semantic-doc-ci
Date: 2026-03-29
Status: completed

## Goal
An LLM-powered CI check that ensures documentation (Markdown files and code comments)
stays in sync with the actual code, blocking PRs on semantic drift.

## Requirements
- Check that all .md files accurately reflect the current state of the code
- Check that inline code comments are consistent with the code they annotate
- Output clear, actionable findings first (what is drifted and how to fix it)
- Then apply fixes automatically where possible
- Must pass before any PR can be merged (hard blocker in CI)
- Must leverage an LLM for semantic understanding (not just regex/AST)

## Out of scope
- Spell checking or grammar linting (that's a different tool)
- Checking docs that are explicitly marked as historical/archival
- Enforcing a particular writing style

## Open questions
- Which LLM and how to authenticate in CI (API key secret)?
- Full repo scan on every PR, or only diff-scoped to changed files?
- How to surface findings — PR comment, check annotation, or both?
- What is the acceptable latency budget for this check in CI?

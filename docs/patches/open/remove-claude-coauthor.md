# Patch: remove-claude-coauthor
Type: chore
Date opened: 2026-03-29

## Problem
All commits include a `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
trailer. Commits should appear as coming from the repo owner, not tagged with
the AI tool used to produce them.

## Fix
- Remove the `Co-Authored-By` trailer from all future commit messages
- Update `CLAUDE.md` to explicitly prohibit adding it

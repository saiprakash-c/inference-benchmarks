# Patch: remove-claude-coauthor
Type: chore
Date opened: 2026-03-29
Date completed: 2026-04-04

## Problem
All commits included a `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
trailer. Commits should appear as coming from the repo owner, not tagged with
the AI tool used to produce them.

## Fix
Added prohibition to CONTEXT.md (and by symlink, CLAUDE.md):
`Never add Co-Authored-By trailers to commits — commits appear as the repo owner's`

## Lessons
None — straightforward doc-only change.

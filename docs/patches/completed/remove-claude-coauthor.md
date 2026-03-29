# Patch: remove-claude-coauthor
Type: chore
Date opened: 2026-03-29

## Problem
All commits include a `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
trailer. Commits should appear as coming from the repo owner, not tagged with
the AI tool used to produce them.

## Fix
- Remove the `Co-Authored-By` trailer from all future commit messages
- `CONTEXT.md` already updated with the prohibition in this PR; `CLAUDE.md` is a
  symlink to `CONTEXT.md` so no separate change needed

Date completed: 2026-03-29

## Lessons learned

No commit template (.gitmessage), commit-msg hook, or script was injecting the trailer.
The trailer was being appended by the Claude Code tool itself (default system prompt
behavior). The fix is purely at the documentation/instruction level: the prohibition
in CONTEXT.md (and its symlink CLAUDE.md / AGENTS.md) is the mechanism that prevents
the trailer from appearing in future commits. Verified no hooks or configs existed that
would need removal.

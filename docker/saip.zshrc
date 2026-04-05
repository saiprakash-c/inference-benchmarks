# ── git safe directory (Docker volume mounts may have uid mismatch) ──────────
git config --global --add safe.directory /workspace 2>/dev/null

# ── colored prompt ────────────────────────────────────────────────────────────
_git_branch() { git -C "$PWD" branch --show-current 2>/dev/null; }
_branch_part() { local b; b=$(_git_branch); [ -n "$b" ] && printf "  (%s)" "$b"; }

setopt PROMPT_SUBST
PROMPT='%B%F{green}%n@%m%f%b:%B%F{blue}%~%f%b%F{yellow}$(_branch_part)%f%# '

# ── persistent history ─────────────────────────────────────────────────────────
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=20000
setopt APPEND_HISTORY SHARE_HISTORY HIST_IGNORE_DUPS HIST_IGNORE_ALL_DUPS

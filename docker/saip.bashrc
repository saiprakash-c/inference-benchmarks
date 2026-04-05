# ── colored prompt: mirrors agnoster (path=blue, branch=yellow) ───────────────
_git_branch() { git -C "$PWD" branch --show-current 2>/dev/null; }
_branch_part() { local b; b=$(_git_branch); [ -n "$b" ] && printf "  (%s)" "$b"; }

_RESET=$'\033[0m'
_BOLD=$'\033[1m'
_GREEN=$'\033[32m'
_BLUE=$'\033[34m'
_YELLOW=$'\033[33m'

PS1="\[${_BOLD}${_GREEN}\]\u@\h\[${_RESET}\]:\[${_BOLD}${_BLUE}\]\w\[${_RESET}\]\[${_YELLOW}\]\$(_branch_part)\[${_RESET}\]\$ "

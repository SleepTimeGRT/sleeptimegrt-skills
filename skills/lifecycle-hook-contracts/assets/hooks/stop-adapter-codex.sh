#!/usr/bin/env bash
# lifecycle-hook-contracts: canonical .codex/hooks/stop.sh v1 — do not
# hand-edit in the target repository; change the copy in sleeptimegrt-skills
# and re-apply.
#
# Codex Stop hook adapter — see references/protocol-contracts.md for the
# verified contract this implements: exit 0 + stdout `{}` lets the turn
# end; exit 2 + a stderr diagnostic asks Codex to keep working (documented
# explicitly as an alternative to the JSON decision path).
#
# `set -e` is intentionally omitted: `status=$?` below reads the exit code
# of a failing `token_gate_capture` call, and under `errexit` a nonzero
# command-substitution assignment exits the shell before that line runs.
set -uo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'lifecycle-hook-contracts: not inside a Git worktree\n' >&2
  exit 2
}

STOP_HOOK_CMD="pnpm verify:static"
# shellcheck source=/dev/null
[ -f "$REPO_ROOT/scripts/lifecycle-hook.conf" ] && . "$REPO_ROOT/scripts/lifecycle-hook.conf"

# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/token-gate.sh"

gate_output=$(cd "$REPO_ROOT" && token_gate_capture stop -- sh -c "$STOP_HOOK_CMD")
status=$?

if [ "$status" -eq 0 ]; then
  printf '{}\n'
  exit 0
fi

printf '%s\n' "$gate_output" >&2
exit 2

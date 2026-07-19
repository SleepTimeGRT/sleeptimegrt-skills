#!/usr/bin/env bash
# Source this file from a non-interactive repository gate.

token_gate_begin() {
  if [ "$#" -ne 1 ]; then
    printf '%s\n' "token_gate_begin: expected an entrypoint name" >&2
    return 64
  fi

  TOKEN_GATE_NAME=$1
  TOKEN_GATE_SAFE_NAME=$(printf '%s' "$TOKEN_GATE_NAME" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')
  TOKEN_GATE_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    printf '[%s] FAIL setup — not inside a Git worktree\n' "$TOKEN_GATE_NAME" >&2
    return 2
  }
  TOKEN_GATE_RAW_LOG=$(cd "$TOKEN_GATE_ROOT" && git rev-parse --git-path "token-gates/$TOKEN_GATE_SAFE_NAME/latest.log") || return $?
  case "$TOKEN_GATE_RAW_LOG" in
    /*) TOKEN_GATE_LOG=$TOKEN_GATE_RAW_LOG ;;
    *) TOKEN_GATE_LOG=$TOKEN_GATE_ROOT/$TOKEN_GATE_RAW_LOG ;;
  esac
  TOKEN_GATE_LOG_DIR=${TOKEN_GATE_LOG%/*}

  token_gate_old_umask=$(umask)
  umask 077
  mkdir -p "$TOKEN_GATE_LOG_DIR" || return $?
  : >"$TOKEN_GATE_LOG" || return $?
  chmod 600 "$TOKEN_GATE_LOG" || return $?
  for token_gate_stale in "$TOKEN_GATE_LOG_DIR"/.stage.*; do
    [ -f "$token_gate_stale" ] && rm -f -- "$token_gate_stale"
  done
  umask "$token_gate_old_umask"

  TOKEN_GATE_PASS_COUNT=0
  TOKEN_GATE_WARN_COUNT=0
  TOKEN_GATE_SKIP_COUNT=0
  TOKEN_GATE_FAIL_COUNT=0
  TOKEN_GATE_STAGE_COUNT=0
  export TOKEN_GATE_NAME TOKEN_GATE_LOG TOKEN_GATE_LOG_DIR
}

token_gate_stage() {
  token_gate_warn_regex=
  if [ "${1-}" = "--warn-regex" ]; then
    if [ "$#" -lt 4 ]; then
      printf '[%s] FAIL setup — --warn-regex requires a pattern, stage, and command\n' "$TOKEN_GATE_NAME" >&2
      return 64
    fi
    token_gate_warn_regex=$2
    shift 2
  fi
  if [ "$#" -lt 3 ] || [ "${2-}" != "--" ]; then
    printf '[%s] FAIL setup — expected: token_gate_stage [--warn-regex REGEX] STAGE -- COMMAND...\n' "$TOKEN_GATE_NAME" >&2
    return 64
  fi
  token_gate_stage_name=$1
  shift 2

  token_gate_old_umask=$(umask)
  umask 077
  token_gate_stage_log=$(mktemp "$TOKEN_GATE_LOG_DIR/.stage.XXXXXX") || return $?
  umask "$token_gate_old_umask"
  token_gate_start=$SECONDS
  if "$@" >"$token_gate_stage_log" 2>&1; then
    token_gate_status=0
  else
    token_gate_status=$?
  fi
  token_gate_elapsed=$((SECONDS - token_gate_start))

  {
    printf '===== %s =====\n' "$token_gate_stage_name"
    cat "$token_gate_stage_log"
  } >>"$TOKEN_GATE_LOG"
  TOKEN_GATE_STAGE_COUNT=$((TOKEN_GATE_STAGE_COUNT + 1))

  if [ "$token_gate_status" -ne 0 ]; then
    TOKEN_GATE_FAIL_COUNT=$((TOKEN_GATE_FAIL_COUNT + 1))
    if [ "$token_gate_status" -gt 128 ] && [ "$token_gate_status" -le 192 ]; then
      token_gate_signal_number=$((token_gate_status - 128))
      token_gate_signal_name=$(kill -l "$token_gate_signal_number" 2>/dev/null || printf '%s' "$token_gate_signal_number")
      printf '[%s] FAIL %s (signal %s, %ss) — log: %s\n' \
        "$TOKEN_GATE_NAME" "$token_gate_stage_name" "$token_gate_signal_name" "$token_gate_elapsed" "$TOKEN_GATE_LOG"
      rm -f -- "$token_gate_stage_log"
      kill -"$token_gate_signal_number" "$$"
      return "$token_gate_status"
    fi
    printf '[%s] FAIL %s (exit %s, %ss) — log: %s\n' \
      "$TOKEN_GATE_NAME" "$token_gate_stage_name" "$token_gate_status" "$token_gate_elapsed" "$TOKEN_GATE_LOG"
    rm -f -- "$token_gate_stage_log"
    return "$token_gate_status"
  fi

  if [ -n "$token_gate_warn_regex" ] && grep -E -q -- "$token_gate_warn_regex" "$token_gate_stage_log"; then
    TOKEN_GATE_WARN_COUNT=$((TOKEN_GATE_WARN_COUNT + 1))
    printf '[%s] WARN %s (%ss) — log: %s\n' \
      "$TOKEN_GATE_NAME" "$token_gate_stage_name" "$token_gate_elapsed" "$TOKEN_GATE_LOG"
  else
    TOKEN_GATE_PASS_COUNT=$((TOKEN_GATE_PASS_COUNT + 1))
    printf '[%s] PASS %s (%ss)\n' "$TOKEN_GATE_NAME" "$token_gate_stage_name" "$token_gate_elapsed"
  fi
  rm -f -- "$token_gate_stage_log"
}

token_gate_skip() {
  if [ "$#" -ne 2 ]; then
    printf '[%s] FAIL setup — expected: token_gate_skip STAGE REASON\n' "$TOKEN_GATE_NAME" >&2
    return 64
  fi
  token_gate_skip_stage=$1
  token_gate_skip_reason=$(printf '%s' "$2" | tr '\r\n' '  ')
  TOKEN_GATE_SKIP_COUNT=$((TOKEN_GATE_SKIP_COUNT + 1))
  TOKEN_GATE_STAGE_COUNT=$((TOKEN_GATE_STAGE_COUNT + 1))
  printf '===== %s (SKIP) =====\n%s\n' "$token_gate_skip_stage" "$token_gate_skip_reason" >>"$TOKEN_GATE_LOG"
  printf '[%s] SKIP %s — %s\n' "$TOKEN_GATE_NAME" "$token_gate_skip_stage" "$token_gate_skip_reason"
}

token_gate_finish() {
  if [ "${TOKEN_GATE_FAIL_COUNT:-0}" -gt 0 ]; then
    token_gate_result=FAIL
  elif [ "${TOKEN_GATE_WARN_COUNT:-0}" -gt 0 ] || [ "${TOKEN_GATE_SKIP_COUNT:-0}" -gt 0 ]; then
    token_gate_result=WARN
  else
    token_gate_result=PASS
  fi
  printf '[%s] %s %s stages — log: %s\n' \
    "$TOKEN_GATE_NAME" "$token_gate_result" "${TOKEN_GATE_STAGE_COUNT:-0}" "$TOKEN_GATE_LOG"
  [ "${TOKEN_GATE_FAIL_COUNT:-0}" -eq 0 ]
}

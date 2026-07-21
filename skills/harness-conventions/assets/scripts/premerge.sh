#!/usr/bin/env bash
# harness-conventions: canonical scripts/premerge.sh v1 — do not hand-edit in the
# target repository; change the copy in sleeptimegrt-skills and re-apply.
#
# The merge gate. Run from the PR branch's worktree before `gh pr merge --squash`.
# Self-merge policy: an agent may merge its own PR only when this script prints PASS.
# Merge one PR at a time; if origin/<default> moves after PASS, re-run.
#
# Exit codes:
#   0  PASS — merge allowed
#   2  precondition failed (dirty tree / behind default branch / empty diff)
#   3  PROTECTED — diff touches gate-integrity paths; a human must merge this PR
#   4  REVIEW — code changes present and --review-done not given; run the
#      cross-model review gate first, then re-run with --review-done
#   *  verify/e2e failure (their exit codes pass through)
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
. "$REPO_ROOT/scripts/token-gate.sh"

# ---- repo config (scripts/premerge.conf.sh overrides these defaults) --------
VERIFY_CMD="pnpm verify"
E2E_CMD="" # e.g. "pnpm test:e2e:ci"; empty = repo has no merge-blocking e2e
REVIEW_EXEMPT_REGEX='(^|/)docs/|\.(md|mdx|txt)$'
PROTECTED_EXTRA_REGEX="" # repo-specific additions to the protected set
CONF="$REPO_ROOT/scripts/premerge.conf.sh"
[ -f "$CONF" ] && . "$CONF"

REVIEW_DONE=0
for arg in "$@"; do
  case "$arg" in
    --review-done) REVIEW_DONE=1 ;;
    *)
      printf 'premerge: unknown argument %s\n' "$arg" >&2
      exit 64
      ;;
  esac
done

# ---- 1. preconditions --------------------------------------------------------
# Verify must run against exactly the committed state that will be merged.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  printf '[premerge] FAIL — uncommitted tracked changes; commit or stash first\n' >&2
  exit 2
fi

DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
[ -z "$DEFAULT_BRANCH" ] && DEFAULT_BRANCH=main
git fetch --quiet origin "$DEFAULT_BRANCH"

# Green against a stale main is not green: two branches can each pass alone and
# fail combined. Require the branch to already contain origin/<default>.
if ! git merge-base --is-ancestor "origin/$DEFAULT_BRANCH" HEAD; then
  printf '[premerge] FAIL — branch is behind origin/%s; merge or rebase it in, then re-run\n' "$DEFAULT_BRANCH" >&2
  exit 2
fi

CHANGED=$(git diff --name-only "origin/$DEFAULT_BRANCH..HEAD")
if [ -z "$CHANGED" ]; then
  printf '[premerge] FAIL — no changes vs origin/%s; nothing to merge\n' "$DEFAULT_BRANCH" >&2
  exit 2
fi

# ---- 2. gate integrity --------------------------------------------------------
# The gate an agent is judged by must not be editable by that agent in the same PR
# (a green result must mean "code is correct", never "gate was weakened").
PROTECTED_REGEX='^\.githooks/|^scripts/(premerge\.sh|premerge\.conf\.sh|token-gate\.sh)$|^biome\.json$|^\.gitleaks\.toml$'
PROTECTED_HITS=$(printf '%s\n' "$CHANGED" | grep -E "$PROTECTED_REGEX" || true)
if [ -n "$PROTECTED_EXTRA_REGEX" ]; then
  EXTRA_HITS=$(printf '%s\n' "$CHANGED" | grep -E "$PROTECTED_EXTRA_REGEX" || true)
  PROTECTED_HITS=$(printf '%s\n%s\n' "$PROTECTED_HITS" "$EXTRA_HITS" | sed '/^$/d' | sort -u)
fi

# The root package.json "scripts" block defines the verify chain itself.
if printf '%s\n' "$CHANGED" | grep -qx 'package.json'; then
  OLD_SCRIPTS=$(git show "origin/$DEFAULT_BRANCH:package.json" |
    node -e 'let d="";process.stdin.on("data",c=>d+=c).on("end",()=>console.log(JSON.stringify(JSON.parse(d).scripts||{})))')
  NEW_SCRIPTS=$(node -e 'console.log(JSON.stringify(require("./package.json").scripts||{}))')
  if [ "$OLD_SCRIPTS" != "$NEW_SCRIPTS" ]; then
    PROTECTED_HITS=$(printf '%s\npackage.json (scripts block)\n' "$PROTECTED_HITS" | sed '/^$/d')
  fi
fi

if [ -n "$PROTECTED_HITS" ]; then
  printf '[premerge] PROTECTED — this PR changes gate-integrity paths:\n'
  printf '%s\n' "$PROTECTED_HITS" | sed 's/^/[premerge]   /'
  printf '[premerge] self-merge is not allowed for gate changes; escalate — a human merges this PR\n'
  exit 3
fi

# ---- 3. cross-model review requirement ----------------------------------------
CODE_CHANGES=$(printf '%s\n' "$CHANGED" | grep -Ev "$REVIEW_EXEMPT_REGEX" || true)
if [ -n "$CODE_CHANGES" ] && [ "$REVIEW_DONE" -ne 1 ]; then
  CODE_COUNT=$(printf '%s\n' "$CODE_CHANGES" | wc -l | tr -d ' ')
  printf '[premerge] REVIEW required — %s code file(s) changed\n' "$CODE_COUNT"
  printf '[premerge] run the cross-model review gate (orca-review-gate), resolve blocking findings,\n'
  printf '[premerge] then re-run: scripts/premerge.sh --review-done\n'
  exit 4
fi

# ---- 4. full verification -------------------------------------------------------
# *_CMD strings run through `bash -c` so quoting inside them behaves like a shell line.
token_gate_capture premerge:verify -- bash -c "$VERIFY_CMD"
if [ -n "$E2E_CMD" ]; then
  token_gate_capture premerge:e2e -- bash -c "$E2E_CMD"
fi

printf '[premerge] PASS — self-merge allowed (squash only, one PR at a time; re-run if origin/%s moves)\n' "$DEFAULT_BRANCH"

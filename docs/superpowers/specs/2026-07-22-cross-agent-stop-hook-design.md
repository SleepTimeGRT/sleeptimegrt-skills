# Cross-agent Stop hook contract — design

- Issue: [SleepTimeGRT/sleeptimegrt-skills#1](https://github.com/SleepTimeGRT/sleeptimegrt-skills/issues/1)
- Date: 2026-07-22

## Problem

A repo-local Stop hook script is wired into both `.claude/settings.json` and
`.codex/hooks.json` in the Medicount pilot repository, running the same
command (Biome auto-fix, Biome check, typecheck) for both runtimes. On
success it prints `{"decision":"approve"}` and exits 0. Codex reports
`hook returned invalid stop hook JSON output` on every successful Stop,
because `"approve"` is not a value either runtime's Stop contract accepts —
this is not a Claude-vs-Codex format mismatch, it is a script written against
a decision vocabulary that exists in neither runtime.

The systemic gap: `harness-conventions` owns Git-native hooks
(pre-commit/pre-push/premerge) and audits them by canonical-file hash. It has
no concept of agent-runtime lifecycle hooks (`.claude/settings.json`,
`.codex/hooks.json`), so nothing in the shared harness can catch an
unsupported response value, a cwd-relative launcher, or a script shared
across runtimes without a tested compatibility contract — before it reaches
a product repository.

This gap was a deliberate, recorded exclusion during the 2026-07-21
three-repo harness unification (`.claude/settings.json` per-repo hooks were
explicitly left out of unification at that time). This spec does not reopen
that exclusion for hook *registration* — which hooks a repo wires up stays
repo-owned. It closes the narrower gap the exclusion left: a shared script's
*response protocol* has no contract, adapter, or audit.

## Verified protocol facts (fetched and quoted 2026-07-22)

Fetched directly from the two runtimes' official hook docs this session —
not carried over from the issue's own (partially inaccurate) summary of them.

| | Claude Code `Stop` | Codex `Stop` |
|---|---|---|
| Allow stop | exit 0. stdout parsed for JSON fields; a documented example uses exit 0 with no output for "no decision; normal permission flow applies" | exit 0 **and** stdout must be JSON — "Stop expects JSON on stdout when it exits 0. Plain text output is invalid for this event." |
| Block / keep working | `{"decision":"block","reason":"..."}`, **or** exit 2 — stdout/JSON is ignored entirely, stderr text is fed back to the agent as the reason, "Prevents Claude from stopping, continues the conversation" | `{"decision":"block","reason":"..."}`, **or** exit 2 + reason on stderr (documented explicitly as an alternative to the JSON path) |
| Valid `decision` values | `"block"` only | `"block"` only — docs explicitly call `"approve"` invalid, "legacy PreToolUse syntax" |
| Hook cwd | not documented | "Commands run with the session `cwd`" — confirms the cwd-relative-launcher bug's root cause |

Sources: `code.claude.com/docs/en/hooks`, `learn.chatgpt.com/docs/hooks`.

**Derived common subset** (this is a synthesis, not a directly-quoted "common
subset" from either doc):

- **Allow stop**: exit 0 + print `{}` to stdout. Empty/no output is not used,
  since Codex's docs explicitly reject plain (non-JSON) stdout on exit 0 and
  it's undocumented whether a truly empty stream counts as "JSON" — `{}` is
  the conservative choice that satisfies both runtimes without ambiguity.
- **Block / keep working**: exit code 2 + a human-readable diagnostic on
  stderr. Both runtimes document this exact path with no runtime-specific
  JSON schema required.
- No `decision` field is emitted by either adapter under this contract.

### Antigravity — investigated, out of scope

Antigravity (`antigravity.google/docs/hooks`, fetched 2026-07-22) has a
**third, distinct** Stop contract: `decision` is required in the JSON stdout
response, and the value to keep working is `"continue"` (neither `"block"`
nor `"approve"`). No exit-code-2 stderr alternative is documented, and hook
cwd is undocumented. It is neither "same style as Codex" nor "unaffected by
this bug class" — it's simply a third shape that issue #1 never mentioned
and that would need its own adapter with different logic (a real JSON
response is mandatory; there is no documented escape hatch to a plain
exit-code/stderr path). Bringing it in now would require materially more
research than this issue asks for. The architecture below (protocol-neutral
core + thin per-runtime adapters) already accommodates adding a third
adapter later without any redesign — this is a deferred extension, not a
closed door.

## Scope

- Stop hook only. Other lifecycle events (Notification, PreToolUse,
  PostToolUse, ...) are out of scope until a real need appears (YAGNI) —
  the current bug and every acceptance criterion in issue #1 are Stop-only.
- Claude Code and Codex only (see Antigravity note above).
- Deliverable is the canonical skill (assets, audit, fixtures) in this repo.
  Applying it to Medicount or any other pilot repo is explicitly out of
  scope for this spec, per the issue's own "Out of scope" section and this
  repo's standing rule to audit first and apply only on explicit request.

## Architecture

New skill, separate from `harness-conventions`: **`lifecycle-hook-contracts`**
(working name — open to change). `harness-conventions` keeps owning only
Git-native hooks; this skill owns agent-runtime lifecycle hook contracts,
adapters, and their audit. This mirrors the existing boundary pattern in the
repo (`token-efficient-gates` owns output economics, `remote-ci-economics`
owns remote CI judgment, `harness-conventions` owns Git hooks — one skill per
protocol domain).

**Dependency**: this skill assumes `harness-conventions` is already applied
to the target repo — specifically that `scripts/token-gate.sh` and a
`verify:static` package script both exist. It does not ship its own copy of
`token-gate.sh`; it sources the one `harness-conventions` already installs.
A repo without `harness-conventions` applied is not a supported target yet.

The validation core is **not modified**. Each adapter wraps the existing,
unmodified `token_gate_capture`/`token_gate_finish` (from
`token-efficient-gates`, copied into a repo the same way `harness-conventions`
already copies `token-gate.sh` today) inside a command substitution, so the
engine's own chatty stdout never reaches the hook's real stdout — only its
exit status is read. The adapter then emits exactly the two-outcome protocol
above:

```sh
REPO_ROOT=$(git rev-parse --show-toplevel)   # cwd-independent — fixes the
                                              # subdirectory/worktree bug
. "$REPO_ROOT/scripts/token-gate.sh"
gate_output=$(cd "$REPO_ROOT" && token_gate_capture stop -- sh -c "$STOP_HOOK_CMD")
status=$?
if [ "$status" -eq 0 ]; then
  printf '{}\n'
  exit 0
else
  printf '%s\n' "$gate_output" >&2
  exit 2
fi
```

- The actual validation command (Biome/typecheck/etc.) is untouched and
  stays repo-owned. Default is `pnpm verify:static` — already the
  `harness-conventions` naming-contract script for exactly this kind of
  static-only check — overridable via a repo-editable `lifecycle-hook.conf`
  (`STOP_HOOK_CMD=...`), following the same repo-owned-config pattern as
  `premerge.conf.sh` / `pre-push.conf`.
  - If a repo has not adopted `harness-conventions` and has no
    `verify:static` script, `token_gate_capture` surfaces that as a FAIL
    (command not found) — routed to stderr/exit 2 like any other failure,
    not silently treated as success.
- Claude Code and Codex adapters are logically near-identical today (both
  reduce to exit-0/`{}` and exit-2/stderr), but are kept as two separate
  canonical files so each is independently hash-audited and fixture-tested,
  matching the issue's acceptance criterion that each runtime have a
  separately tested adapter, and so they can diverge later without
  entangling each other.

## Components

```
skills/lifecycle-hook-contracts/
  SKILL.md
  assets/
    hooks/
      stop-adapter-claude.sh   # installed at .claude/hooks/stop.sh
      stop-adapter-codex.sh    # installed at .codex/hooks/stop.sh
    lifecycle-hook.conf        # repo-editable: STOP_HOOK_CMD override
                                # (default: pnpm verify:static)
  scripts/
    audit.py                  # same CLI shape as harness-conventions:
                                # --repo <target> [--format json]
  references/
    protocol-contracts.md     # the verified table above, with doc citations
                                # and fetch date, kept current as docs change
tests/
  test_lifecycle_hook_contracts.py
```

## Audit checks (`scripts/audit.py`)

Read-only, same shape as `harness-conventions/scripts/audit.py` (hash
comparison against canonical assets, PASS/WARN/FAIL/DRIFT/MISSING severities).

1. If `.claude/settings.json` and `.codex/hooks.json` both register a Stop
   hook pointing at the same underlying script, and that script's hash
   doesn't match the canonical adapter for its runtime → **FAIL** — "shared
   script has no tested cross-runtime adapter."
2. Static scan of the registered script(s) for a `"decision"` value other
   than the runtime's documented one (e.g. `"approve"`) → **FAIL** — this is
   the direct regression check for the bug that opened issue #1.
3. Detect a cwd-relative launcher (a command invoking a relative script path
   with no `git rev-parse --show-toplevel` resolution) → **FAIL**.
4. Detect mixed signaling — JSON stdout paired with an exit code other than
   0 or 2 → **WARN**.

## Data flow

1. Claude Code (or Codex) fires Stop → runs the runtime's canonical adapter,
   with the session's actual cwd (which may be the repo root, a
   subdirectory, or a worktree).
2. Adapter resolves `REPO_ROOT` via `git rev-parse --show-toplevel`,
   independent of step 1's cwd.
3. Adapter runs the configured validation command through the unmodified
   `token_gate_capture`, inside a command substitution.
4. Exit 0 (PASS or WARN, per existing `token_gate_finish` semantics) →
   stdout `{}`, exit 0 → the runtime lets the turn end.
5. Exit nonzero (FAIL) → the captured PASS/FAIL summary and bounded log path
   (the same diagnostic text engineers already see from git hooks) goes to
   stderr, exit 2 → the runtime feeds it back and keeps the agent working.

## Error handling

- `git rev-parse --show-toplevel` fails (not inside a Git worktree) → fail
  closed: exit 2 with a stderr diagnostic, not a silent exit 0. There is
  nothing to validate reliably in that state, so it should surface rather
  than approve.
- Configured validation command missing or misconfigured →
  `token_gate_capture` already reports this as a FAIL; routed to stderr/exit
  2 like any other failure.
- Validation command killed by a signal → exact behavior is verified by the
  fixture suite rather than fixed in this spec (real shell/signal semantics
  inside a command-substitution wrapper are subtle enough to need a test,
  not a paper guarantee).

## Testing (maps to issue #1 acceptance criteria)

Follows the existing `GitFixture` pattern from
`tests/test_token_efficient_gates.py` (temporary git repo, path containing
spaces).

- A fixture script that prints `{"decision":"approve"}` and exits 0 is
  audited and flagged FAIL — reproduces the original bug as a regression
  test.
- Adapter run against a passing validation stub: stdout is exactly `{}`,
  stderr empty, exit 0.
- Adapter run against a failing validation stub: stdout empty, stderr
  carries the diagnostic, exit 2.
- Adapter run from the repo root, a nested subdirectory, and a worktree path
  containing spaces — all three resolve the same repo root and behave
  identically.
- Audit distinguishes a cwd-relative launcher from a canonical adapter path.
- Audit distinguishes a hash-matching canonical script from a drifted one
  shared across both runtime configs.

## Boundaries

- `harness-conventions` — unchanged; still owns only Git-native hooks
  (pre-commit/pre-push/premerge). Does not gain a lifecycle-hook asset.
- `token-efficient-gates` — owns the capture engine (`token-gate.sh`) this
  skill wraps. This skill does not modify or fork it.
- `lifecycle-hook-contracts` (this skill) — owns the Stop hook protocol
  contract, its Claude Code/Codex adapters, cwd-safe entrypoint resolution,
  and the cross-runtime compatibility audit. A third (Antigravity) adapter
  is future work, gated on dedicated research into its actual contract.

## Apply workflow (deferred)

Not executed as part of this spec. When a user explicitly requests rollout
to a pilot repo, the flow mirrors `harness-conventions`'s existing one:
audit first, copy the two adapter scripts and `lifecycle-hook.conf`, wire
`.claude/settings.json` / `.codex/hooks.json` to point at the adapters
instead of the raw validation script, re-run the audit until COMPLIANT, then
verify by observing a real Stop fire in each runtime.

## Out of scope

- Weakening or removing the existing Biome/typecheck validation stages.
- Unifying what hooks a repo registers in `.claude/settings.json` — that
  stays repo-owned, per the 2026-07-21 decision.
- Antigravity adapter (see note above).
- Applying any of this to Medicount or other product repos before the
  canonical assets and fixtures here are complete.

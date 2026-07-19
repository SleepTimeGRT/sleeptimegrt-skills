---
name: token-efficient-gates
description: Audit and reduce agent input-token waste caused by verbose local non-interactive engineering commands. Use when Git hooks, pre-commit/pre-push, local verify or pre-merge scripts, test/lint/typecheck commands, tracked shell files, or package-script call chains flood agent terminal context; when output volume must be measured without forwarding raw logs; or when compact PASS/WARN/FAIL/SKIP summaries with recoverable diagnostics should be installed. Excludes remote CI runner minutes, billing, workflow scheduling, matrices, caches, and artifact economics.
---

# Token-Efficient Gates

Reduce agent-facing verification output while preserving evidence and command semantics.

## Keep the target separate

Treat this skill repository as the source of reusable tooling, not as the target. Resolve and state the target repository before working.

Choose one mode:

- **Audit**: inspect local gate call chains without executing them.
- **Measure**: execute one verified-safe gate while redirecting all raw output away from agent context.
- **Apply**: install compact output behavior in user-approved target files.

Default to Audit. Do not turn inspection into Measure or Apply implicitly.

## Audit local token surfaces

1. Record the target root and `git status --short`.
2. Run `scripts/audit.py --repo <target> --format json`.
3. Follow `call_edges` from hooks, verify scripts, pre-merge scripts, and related package commands. Inspect only the chains relevant to recurring agent execution.
4. Verify stage order, conditional behavior, warning behavior, fail-fast versus aggregate failure, exit codes, and signal handling from source.
5. Treat `interactive`, `release-deploy`, `destructive-data`, and non-empty `safety_signals` as exclusion boundaries until manually resolved.
6. Report output volume as unmeasured unless a captured log or Measure run provides evidence.
7. Re-run `git status --short`. Audit mode must not change the target repository.

The audit intentionally ignores `.github/workflows` and remote CI economics. A local command named `ci` remains in scope only as an agent-executed command surface.

## Measure without spending context

Measure only after verifying the complete call chain is non-interactive and does not deploy, publish, migrate, seed, reset, wipe, or write external state.

```bash
python3 <skill-dir>/scripts/measure.py \
  --repo <target> \
  --label pre-push \
  -- <command> <arg>...
```

The helper invokes argv directly, writes combined stdout/stderr to a worktree-specific `latest.log` inside Git's internal path, and returns only JSON containing outcome, exit code, duration, line count, byte count, and log path. It does not interpret shell operators. Use `bash -lc` only when the reviewed command genuinely requires shell syntax.

Distinguish measurements:

- `output_bytes` and `output_lines` are measured terminal output.
- Agent tool-output tokens are known only when the harness reports them.
- Model input tokens are known only when the model/harness reports them.

Do not invent a byte-to-token conversion. Use line/byte reduction as a directional proxy unless token counts are directly observed.

Inspect diagnostics progressively with targeted `rg`, `tail`, or stage-specific reads. Do not stream the entire measurement log back into agent context.

## Report the opportunity

Use a compact evidence-first report:

```text
Target: <absolute path>
Mode: audit | measure

Recurring gate
- Entry point: <path or package script>
- Verified stages: <ordered call chain>
- Current output: <measured lines/bytes/tool tokens, or unmeasured>
- Semantics to preserve: <warnings, exit, signal, fail-fast/aggregate>

Recommendation
- Compact: <approved non-interactive stages>
- Keep verbose: <interactive or diagnostic commands>
- Do not run: <release/deploy/migration/destructive paths>
```

Lead with the highest recurring agent-context cost. Do not enumerate unrelated repository scripts.

## Apply an approved change

1. List the exact target files and mechanically record the before-stage sequence.
2. Copy `assets/token-gate.sh` into the target repository, normally under a tracked `tools/` directory. Never reference this skills repository at target runtime.
3. Source the copied asset from approved non-interactive entry points.
4. Wrap one existing command per `token_gate_stage`, preserving command arguments and order verbatim.
5. Use `--warn-regex` only with a narrow warning marker verified for that stage.
6. Preserve existing fail-fast or aggregate-failure behavior. Do not add parallelism, retries, skips, or reordering as part of output compaction.
7. Compare before/after stages mechanically, run representative safe fixtures, verify logs, and confirm clean `git status` after gate execution.

Example fail-fast gate:

```bash
repo_root=$(git rev-parse --show-toplevel) || exit $?
source "$repo_root/tools/token-gate.sh"
token_gate_begin pre-push || exit $?
token_gate_stage typecheck -- pnpm typecheck || exit $?
token_gate_stage --warn-regex 'verified warning marker' spec:vocab -- pnpm spec:vocab || exit $?
token_gate_finish
```

Read [references/output-economics.md](references/output-economics.md) before designing warning detection, diagnostics, measurement claims, or log retention.

## Stop at the remote boundary

Do not review or optimize GitHub Actions minutes, hosted runner billing, workflow triggers, matrices, concurrency, caches, services, or artifacts with this skill. Those belong to the separate remote CI budget economics skill.

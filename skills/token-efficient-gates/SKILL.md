---
name: token-efficient-gates
description: 'Capture and progressively inspect verbose output from agent-run local non-interactive engineering commands. Use whenever Git hooks reached through Git commands, local verify/CI/pre-merge scripts, test, lint, or typecheck commands would flood agent terminal context: passing runs should consume one summary line, while warning or failed runs should expose bounded line-number indexes into a recoverable log. Excludes remote CI runner minutes, billing, workflow scheduling, matrices, caches, and artifact economics.'
---

# Token-Efficient Gates

Reduce output entering agent context, not verification coverage.

## Preserve the original command

Treat the command as opaque by default. Do not split its stages, add or remove flags, replace its package script, or modify its hook merely to compact output.

Resolve the target repository and exact command first. If the command is already authorized and non-interactive, execute that same argv once through the capture helper. Capturing output does not authorize a push, deploy, migration, reset, seed, or other side effect.

## Capture agent-facing output

```bash
python3 <skill-dir>/scripts/capture.py \
  --repo <target> \
  --label verify:ci \
  -- pnpm verify:ci
```

The helper stores combined stdout/stderr in a restrictive, worktree-specific `latest.log` below `${TMPDIR:-/tmp}`. It deletes the log on `PASS`; `WARN` and `FAIL` retain one bounded `latest.log` for diagnosis. It preserves the command exit status and signal behavior.

Consume its result economically:

- `PASS`: stop. Do not locate or read the log. The log path is intentionally omitted.
- `WARN`: use the returned log path and `L<number>` index. Read only the indexed neighborhood.
- `FAIL`: use the returned log path and bounded index. Do not stream the whole log back into context.
- `ERROR`: fix the capture invocation or environment; the target command may not have run.

A failure returns at most five high-confidence diagnostic candidates:

```text
[verify:ci] FAIL (exit 1, 7.013s) — log: <absolute-path>/latest.log
[verify:ci] INDEX L184: src/check.ts:14:3 error TS2322: wrong type
```

If no stable marker is found, the index provides a bounded tail range such as `inspect L716-L735` without printing those lines.

## Preserve meaningful exit-zero warnings

Most exit-zero commands need no log inspection. Some gates encode a meaningful warning only in output. After verifying a narrow stable marker for that command, pass it explicitly:

```bash
python3 <skill-dir>/scripts/capture.py \
  --repo <target> \
  --label spec:vocab \
  --warn-regex '^⚠ spec:vocab' \
  -- pnpm spec:vocab
```

Do not use a universal `warning|warn` detector. False warning matches make agents read successful logs and recreate the token waste this skill exists to prevent.

## Read diagnostics progressively

For each returned index line:

1. Read a small range around that line with `sed -n` or an equivalent bounded reader.
2. Search for one specific filename, test, error code, or marker with bounded `rg` output.
3. Expand to a larger stage or tail range only when the first evidence is insufficient.
4. Read the complete log only as a last resort.

Logs may contain credentials, headers, environment dumps, connection strings, or user data. Do not quote or upload them wholesale.

Read [references/output-economics.md](references/output-economics.md) for index behavior, warning detection, and log safety.

## Audit when execution safety is unclear

Run `scripts/audit.py --repo <target> --format json` before capture when the call chain is unknown. Inspect stage order, conditions, interactive behavior, and side effects without executing the target command.

Do not run deploy, release, migration, seed, wipe, DB reset, E2E infrastructure, or external-write commands merely to measure or compact their output. If the user independently authorized such a command, capture changes only how the agent consumes its output.

## Measure economics separately

Use `scripts/measure.py` only when comparing line and byte volume. Its JSON output is measurement evidence, not the normal agent execution interface.

Terminal bytes, tool-output tokens, and model input tokens are different measurements. Claim only the quantity actually observed.

## Modify a target only by explicit request

The normal workflow changes no tracked target file. Install or edit a repo-local hook or gate only when the user explicitly requests persistent compact behavior for callers that cannot use `capture.py`.

When applying a persistent adapter, preserve stage order, conditions, exit codes, signals, and fail-fast or aggregate-failure behavior. Never make the target repository depend on this skills repository at runtime.

## Stop at the remote boundary

Do not review or optimize GitHub Actions minutes, hosted runner billing, workflow triggers, matrices, concurrency, caches, services, or artifacts with this skill. Those belong to the separate `remote-ci-economics` skill.

# Agent output economics

## Economic target

Optimize repeated output that enters an agent's context, not the amount of verification performed. A passing gate should usually emit one summary line per stage plus a final result. Complete diagnostics should remain available outside the immediate tool response.

Do not claim token savings from line or byte counts alone. Terminal bytes, tool-output tokens, and model input tokens are different measurements. State which one was observed.

## Preserve the verification contract

Before compacting, verify:

1. Entrypoints and nested commands.
2. Stage order and conditional execution.
3. Fail-fast versus continue-and-summarize behavior.
4. Exit codes and signals.
5. Successful commands that emit meaningful warnings.
6. Existing skips and their reasons.

Output refactoring must not remove stages, introduce retries or parallelism, or turn warnings into passes.

## Compact only non-interactive gates

Suitable surfaces include pre-push hooks, local verify commands, deterministic lint/typecheck/test stages, and merge gates an agent runs repeatedly.

Keep development servers, watch mode, debuggers, deploy/release commands, migrations, destructive data commands, and manual diagnostic commands verbose. Their output is part of their interface or their execution is unsafe to perform merely for measurement.

## Reveal diagnostics progressively

Use this order after `WARN` or `FAIL`:

1. Read the one-line stage summary.
2. Search the log for error markers or filenames with bounded `rg` output.
3. Read a bounded tail or the relevant stage section.
4. Read the full log only when narrower evidence is insufficient.

This preserves context for reasoning instead of spending it on successful progress output.

## Detect warnings narrowly

Do not use a universal `warning|warn` pattern. Capture a verified clean success and warning success, then select the narrow stable marker for that tool. Prefer structured output or a documented warning status when available.

## Store logs safely

Use Git-derived internal paths so logs are untracked and linked worktrees remain isolated. Keep one `latest.log` per entry point instead of accumulating timestamps, create it with restrictive permissions, and print a stable absolute path.

Logs can contain credentials, headers, environment dumps, connection strings, or user data. Review command output risk before persisting or sharing a log. Never upload full logs automatically.

## Runner API

`assets/token-gate.sh` provides:

- `token_gate_begin ENTRYPOINT`
- `token_gate_stage [--warn-regex REGEX] STAGE -- COMMAND...`
- `token_gate_skip STAGE REASON`
- `token_gate_finish`

`token_gate_finish` returns `1` when an aggregate gate continued after failures. Commands returning the shell convention `128 + signal` cause the runner to print the failure and re-raise that signal.

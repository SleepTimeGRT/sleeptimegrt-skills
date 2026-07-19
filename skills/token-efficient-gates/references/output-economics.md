# Agent output economics

## Economic target

Optimize repeated output that enters an agent's context, not the amount of verification performed. Keep the original command and arguments intact. Redirect complete stdout/stderr to a recoverable log before the terminal tool can forward it to the model.

The default consumption contract is asymmetric:

- A passing command costs one summary line and no log read.
- A warning or failed command costs one summary plus a small diagnostic index.
- Additional context is purchased only when an indexed read is necessary.

Do not claim token savings from line or byte counts alone. Terminal bytes, tool-output tokens, and model input tokens are different measurements.

## Failure index

`scripts/capture.py` scans a failed log outside model context and returns at most five high-confidence candidates. Each candidate contains:

- the exact one-based log line number;
- a single whitespace-normalized diagnostic snippet;
- at most 180 characters.

The generic detector covers common error, fatal, panic, exception, failed, TAP `not ok`, and failure-symbol markers. It is a navigation aid, not a diagnosis. If it finds no candidate, it returns only the final 20-line range to inspect.

Use the index to make bounded reads such as:

```bash
sed -n '174,194p' '<log-path>'
rg -n -m 10 'TS2322|src/check\.ts' '<log-path>'
```

Do not automatically print the indexed neighborhood. A line number is cheap; its surrounding diagnostics should enter context only when the agent needs them.

## Exit-zero warnings

An exit code of zero normally ends consumption immediately. When a specific command is verified to emit actionable warnings while returning zero, pass a narrow `--warn-regex`. Matching warning lines become the index.

Do not use a universal `warning|warn` pattern. Test names, dependency summaries, and statements such as `0 failed` commonly create false positives.

## Log lifecycle and safety

The capture helper derives a worktree identity from Git but stores output below `${TMPDIR:-/tmp}`. Linked worktrees remain isolated, and each worktree/label pair has one `latest.log` rather than timestamp accumulation. Directories use restrictive permissions and the log is `0600`. A `PASS` deletes the log; `WARN` and `FAIL` retain it and print its path for immediate diagnosis. Temporary storage may be cleared by the operating system, which is appropriate because these logs are diagnostic scratch data rather than durable records.

Logs can contain credentials, headers, environment dumps, connection strings, or user data. Review output risk before capture, never upload logs automatically, and quote only the bounded evidence required for diagnosis.

## Persistent repository adapters

Agent-side capture is the default because it requires no target mutation and cannot change verification stages. A repo-local adapter is a secondary option for callers that cannot intercept the command output. Install one only by explicit request and mechanically verify the original stage, exit, signal, and conditional behavior.

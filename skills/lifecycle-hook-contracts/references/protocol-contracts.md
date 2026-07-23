# Stop hook protocol contracts

Verified directly against each runtime's official hook documentation
(2026-07-22). Keep this current if a runtime changes its contract —
re-fetch and re-quote rather than editing from memory.

## Claude Code (code.claude.com/docs/en/hooks)

- Allow stop: exit 0. stdout is parsed for JSON fields; the docs' own
  example uses `exit 0` with no output for "no decision; normal permission
  flow applies".
- Block / keep working: `{"decision": "block", "reason": "..."}`, **or**
  exit 2 — stdout/JSON is ignored entirely on exit 2, and stderr text is
  fed back to Claude as the reason. Stop-specific effect: "Prevents Claude
  from stopping, continues the conversation."
- Valid `decision` values: `"block"` only.
- `.claude/settings.json` can reference the script via
  `${CLAUDE_PROJECT_DIR}` to avoid depending on session cwd.

## Codex (learn.chatgpt.com/docs/hooks)

- Allow stop: exit 0 **and** stdout must be JSON — "Stop expects JSON on
  stdout when it exits 0. Plain text output is invalid for this event."
  (Specific to `Stop`/`SubagentStop`; other events accept plain text.)
- Block / keep working: `{"decision": "block", "reason": "..."}`, **or**
  exit 2 + reason on stderr — documented explicitly as an alternative to
  the JSON path.
- Valid `decision` values: `"block"` only — `"approve"` is explicitly
  called out as invalid, "legacy PreToolUse syntax."
- Commands run with the session `cwd` — no project-root env var is
  documented; `.codex/hooks.json` commands should resolve the root
  themselves, e.g. `$(git rev-parse --show-toplevel)`.

## Antigravity — not implemented (antigravity.google/docs/hooks)

A third, distinct contract: `decision` is **required** in the stdout JSON,
and the value that keeps the agent working is `"continue"` — neither
`"block"` nor `"approve"`. No exit-code-2 stderr alternative is documented.
No adapter exists for this runtime; see the design spec's "Antigravity"
section for why.

## Derived common subset (this skill's actual behavior)

Not a quotation from either doc — this is what `stop-adapter-claude.sh` and
`stop-adapter-codex.sh` actually emit, chosen to satisfy both verified
contracts unambiguously:

| Outcome | Response |
|---|---|
| Allow stop | exit 0, stdout `{}` |
| Keep working | exit 2, stderr carries a human-readable diagnostic |

No adapter emits a `decision` field.

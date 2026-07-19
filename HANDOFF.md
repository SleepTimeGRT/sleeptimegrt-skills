# Handoff — agent token economics skills

## Current decision

The original composite `quiet-gates` design was split on 2026-07-19 because local agent-context economics and remote CI budget economics have different triggers, evidence, and mutation contracts.

Create two specialized skills:

1. **Agent token economics** — current focus, implemented as `token-efficient-gates`.
2. **Remote CI budget economics** — deferred; do not create an empty placeholder skill.

Do not reintroduce GitHub Actions minutes, runner billing, workflow scheduling, matrices, caches, services, or artifact economics into `token-efficient-gates`.

## Current implementation

`skills/token-efficient-gates/` exists and contains:

- `SKILL.md` — capture-first agent consumption workflow, with Audit and Measure as supporting modes.
- `scripts/audit.py` — read-only tracked hook/shell/package inventory and local call edges. It intentionally ignores `.github/workflows`.
- `scripts/capture.py` — executes the original command unchanged, keeps passing output out of agent context, and returns bounded line-number indexes for warnings or failures.
- `scripts/measure.py` — executes one already-reviewed safe command while redirecting raw output to a worktree-specific `latest.log`; terminal output is one JSON summary.
- `assets/token-gate.sh` — optional standalone repo-local compact runner for explicitly requested persistent adaptations.
- `references/output-economics.md` — measurement provenance, progressive diagnostics, warning, and log guidance.
- `agents/openai.yaml` — UI metadata.

`tests/test_token_efficient_gates.py` contains twenty fixture tests. The suite and official `quick_validate.py` passed on 2026-07-20.

The obsolete `skills/quiet-gates/` folder was removed after the replacement passed.

## Objective

Reduce repeated terminal output that enters agent context without reducing verification coverage or changing the command being run.

The normal solution is agent-side capture, not rewriting `verify`, `verify:ci`, package scripts, or hooks. Preserve the original command and arguments as one opaque invocation. Successful runs return one summary line, delete their temporary log, and require no log read. Warning or failed runs return a bounded `L<number>` diagnostic index into a restrictive `${TMPDIR:-/tmp}` log.

Target local surfaces:

- Git hooks (`pre-commit`, `pre-push`, `pre-merge`)
- agent-executed `verify`, lint, typecheck, test, and local CI entry points
- tracked `.sh` files
- root and workspace `package.json` call chains

Desired non-interactive output:

```text
[verify:ci] PASS (4s)
[verify:ci] WARN (1s) — log: <path>
[verify:ci] INDEX L33: <bounded warning marker>
[verify:ci] FAIL (exit 1, 7s) — log: <path>
[verify:ci] INDEX L184: <bounded failure marker>
```

Full diagnostics remain available in a bounded, restrictive, worktree-safe log. Interactive development, deploy, release, migration, destructive data, and external-write commands are exclusion boundaries rather than compaction targets.

## Measurement provenance

Keep these facts separate:

- Terminal output lines and bytes can be measured by `measure.py`.
- Agent tool-output tokens are known only when the harness reports them.
- Model input tokens are known only when the model/harness reports them.

Do not invent a byte-to-token conversion.

## Verified initiating evidence

The initiating repository was `/Users/minchul/Projects/toss-samhaengsi`.

- `.githooks/pre-push` runs `typecheck → spec:trace → spec:vocab → test:unit → test:tools` and forwards every child command's output.
- A real `git push` previously produced approximately 68,031 reported tool-output tokens before truncation; 40,000 tokens were returned to agent context.
- `.githooks/pre-commit` was already relatively concise.
- `tools/pre-merge-local.sh`, `pnpm verify`, and `tools/e2e-ci.sh` also inherit verbose child output.
- `spec:vocab` can exit successfully while emitting warnings, so binary success/failure output is insufficient.

The token figures above are prior captured evidence, not a measurement repeated by the new helper in the current implementation session.

## First pilot repositories

Use these as explicit read-only targets before applying changes:

1. `/Users/minchul/Projects/toss-samhaengsi`
   - Primary apply candidate: `.githooks/pre-push`.
   - Do not execute E2E merely to measure output; its script owns and kills emulator processes.
2. `/Users/minchul/Projects/medicount`
   - `.husky/pre-push` is already a concise verification-stamp check; do not rewrite it.
   - `scripts/verify-ci.sh` is an aggregate-failure compacting candidate and conditionally performs local DB reset + pgTAP, so measurement requires resolving the safety boundary first.
3. `/Users/minchul/Projects/toss-space-goldrush`
   - Tracked pre-push hook performs no verification; recommend no pre-push rewrite.
   - Remote GitHub workflow economics belong to the deferred second skill.

“All repositories have the same problem” remains false based on the pilots. Inventory before proposing mutations.

## toss-samhaengsi pilot applied

On 2026-07-20 the user explicitly approved a persistent first pilot in `/Users/minchul/Projects/toss-samhaengsi`.

- Added `tools/token-gate.sh` as a target-local copy of the skill asset.
- Wrapped `.githooks/pre-push` with one whole-command capture and a recursion guard; the original five commands remain verbatim and in the same order.
- Added only the verified `^⚠ spec:vocab` exit-zero warning detector.
- Updated `AGENTS.md` with the capture/index behavior.
- Actual safe pre-push run: exit 0, `WARN`, two agent-facing lines, 267 bytes, 84 exact `o200k_base` tokens.
- Previous baseline for the same hook: 7,425 lines and 79,487 exact `o200k_base` tokens. The pilot log remains 7,425 lines and preserves all five stage markers plus final OK.
- Controlled failure fixture: original exit 19 preserved, raw failure hidden, exact failure candidate returned as `INDEX L8`.
- Log mode verified as `0600`; shell syntax, copied-asset equality, `git diff --check`, nineteen skill fixture tests, and official skill validation passed.

A follow-up on 2026-07-20 moved capture logs from Git-internal storage to `${TMPDIR:-/tmp}`. Paths remain worktree/label scoped with one bounded `latest.log`; `PASS` deletes the log, while `WARN` and `FAIL` retain it. The target-local asset was updated with the skill asset, the actual pre-push warning log was verified as `0600`, and the obsolete Git-internal pre-push log was removed. The expanded suite now has twenty tests.

The target pilot changes are `.githooks/pre-push`, `AGENTS.md`, and `tools/token-gate.sh`.

## Runner contract

The primary `scripts/capture.py` contract is:

- Run the exact original argv once without stage decomposition or flag changes.
- On `PASS`, print one summary line without a log path; the agent stops reading.
- On `WARN` or `FAIL`, print the log path and at most five indexed diagnostic candidates with exact one-based line numbers.
- If no failure marker matches, print only the final 20-line range to inspect.
- Detect exit-zero warnings only through an explicitly supplied narrow `--warn-regex`.
- Preserve the original exit code and re-raise terminating signals.

The optional repo-local asset retains this persistent-adapter contract:

- One summary line per completed stage plus a final result.
- Preserve `PASS`, `WARN`, `FAIL`, and `SKIP` distinctly.
- Preserve stage order, conditions, exit codes, signals, and fail-fast or aggregate-failure behavior.
- Store combined stdout/stderr under `${TMPDIR:-/tmp}` with a worktree-derived identity and entrypoint label.
- Use restrictive permissions and one `latest.log` rather than unbounded timestamp accumulation; delete it on `PASS` and retain it only for `WARN` or `FAIL`.
- Keep target repositories independent of `sleeptimegrt-skills` at runtime.
- Use a narrow verified warning detector per stage.

## Acceptance criteria

- Audit executes no target commands and leaves target status unchanged.
- Measure runs only a fully inspected non-interactive, non-external-write command.
- Measure returns only outcome, exit code, duration, lines, bytes, and log path to terminal context.
- Apply changes only user-approved gate paths.
- Full diagnostics remain recoverable through targeted log reads.
- Successful, warning, failed, skipped, signaled, paths-with-spaces, linked-worktree, permission, stale-log, and aggregate-failure fixtures remain green.
- Before/after verification stages are mechanically identical.

## Next work

Focus on the first skill:

1. Re-run the three pilot commands through `scripts/capture.py` without changing their flags or target files.
2. Verify that passing runs stop after one summary line and realistic failures yield useful bounded indexes.
3. Do not prepare target hook or package-script adaptations unless explicitly requested.
4. Forward-test realistic trigger prompts when authorized; no subagent validation has been run yet.

Only after the first skill is accepted should a separately initialized remote CI budget economics skill be designed.

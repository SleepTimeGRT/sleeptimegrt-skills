# Handoff — agent token economics skills

## Current decision

The original composite `quiet-gates` design was split on 2026-07-19 because local agent-context economics and remote CI budget economics have different triggers, evidence, and mutation contracts.

Create two specialized skills:

1. **Agent token economics** — current focus, implemented as `token-efficient-gates`.
2. **Remote CI budget economics** — deferred; do not create an empty placeholder skill.

Do not reintroduce GitHub Actions minutes, runner billing, workflow scheduling, matrices, caches, services, or artifact economics into `token-efficient-gates`.

## Current implementation

`skills/token-efficient-gates/` exists and contains:

- `SKILL.md` — Audit, Measure, and Apply workflow.
- `scripts/audit.py` — read-only tracked hook/shell/package inventory and local call edges. It intentionally ignores `.github/workflows`.
- `scripts/measure.py` — executes one already-reviewed safe command while redirecting raw output to a worktree-specific `latest.log`; terminal output is one JSON summary.
- `assets/token-gate.sh` — standalone repo-local compact runner.
- `references/output-economics.md` — measurement provenance, progressive diagnostics, warning, and log guidance.
- `agents/openai.yaml` — UI metadata.

`tests/test_token_efficient_gates.py` contains eight fixture tests. The suite and official `quick_validate.py` passed on 2026-07-19.

The obsolete `skills/quiet-gates/` folder was removed after the replacement passed.

## Objective

Reduce repeated terminal output that enters agent context without reducing verification coverage.

Target local surfaces:

- Git hooks (`pre-commit`, `pre-push`, `pre-merge`)
- agent-executed `verify`, lint, typecheck, test, and local CI entry points
- tracked `.sh` files
- root and workspace `package.json` call chains

Desired non-interactive output:

```text
[verify] PASS typecheck (4s)
[verify] WARN spec:vocab (1s) — log: <path>
[verify] FAIL test:unit (exit 1, 7s) — log: <path>
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

## Runner contract

- One summary line per completed stage plus a final result.
- Preserve `PASS`, `WARN`, `FAIL`, and `SKIP` distinctly.
- Preserve stage order, conditions, exit codes, signals, and fail-fast or aggregate-failure behavior.
- Store combined stdout/stderr under `git rev-parse --git-path "token-gates/<entrypoint>/latest.log"`.
- Use restrictive permissions and one `latest.log` rather than unbounded timestamp accumulation.
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

1. Run the new compact audit against the three pilot repositories.
2. Review the resulting local gate call chains without running them.
3. Prepare a proposed `toss-samhaengsi` pre-push adaptation, but do not modify that repository without explicit approval.
4. Forward-test realistic trigger prompts when authorized; no subagent validation has been run yet.

Only after the first skill is accepted should a separately initialized remote CI budget economics skill be designed.

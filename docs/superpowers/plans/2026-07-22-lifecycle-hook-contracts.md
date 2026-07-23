# Lifecycle Hook Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: dispatch via `orca-sdd` (this
> user's configured default for executing an SDD implementation plan — see
> the "Orca orchestration workflows" section of their global CLAUDE.md). If
> the Orca runtime is unavailable, fall back to
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans`, per each skill's own fallback rules. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new `lifecycle-hook-contracts` skill — canonical Stop-hook
adapters for Claude Code and Codex, a cross-runtime compatibility audit, and
fixture tests — so a repo-local Stop hook shared across both runtimes can no
longer ship an unsupported response value or a cwd-relative launcher
undetected.

**Architecture:** Each runtime gets its own tiny canonical adapter script
that wraps the existing, unmodified `token_gate_capture` (from
`token-efficient-gates`) inside a command substitution and translates its
exit status into that runtime's verified Stop contract (exit 0 + stdout `{}`
to allow stop; exit 2 + stderr diagnostic to keep working). A companion
`audit.py` statically detects the original bug class (a script shared
verbatim across both runtime configs, an unsupported `decision` value, a
cwd-relative entrypoint, or drift from the canonical adapter).

**Tech Stack:** Bash (adapters, sourcing the existing `token-gate.sh`),
Python 3 stdlib only (`audit.py`, tests — no `pytest`, this repo has none
installed; tests run via `python3 -m unittest`).

## Global Constraints

- Scope is the Stop hook only, for Claude Code and Codex only. Antigravity
  has a third, distinct contract (`decision: "continue"`, no documented
  exit-2 escape hatch) and is explicitly out of scope — do not add a third
  adapter in this plan.
- The verified response contract, from the design spec
  (`docs/superpowers/specs/2026-07-22-cross-agent-stop-hook-design.md`):
  **allow stop** = exit 0 + stdout `{}`; **keep working** = exit 2 + a
  human-readable diagnostic on stderr. No adapter ever emits a `decision`
  field.
- `token-efficient-gates`'s `token_gate_capture`/`token_gate_finish` (in
  `skills/token-efficient-gates/assets/token-gate.sh`) must never be
  modified or forked by this work. Adapters source it as-is.
- This skill assumes a target repo already has `harness-conventions`
  applied (`scripts/token-gate.sh` and a `verify:static` package script
  exist). Do not build a fallback path for repos without it.
- Nothing in this plan is applied to Medicount or any other product repo —
  deliverables stay inside this skills repo (canonical assets, audit,
  fixtures, docs) per the design spec's explicit out-of-scope list.
- One task = one commit. Do not push. Do not touch files outside
  `skills/lifecycle-hook-contracts/`, `tests/test_lifecycle_hook_contracts.py`,
  and this plan/spec's own docs.

---

## Task 1: Protocol contracts reference doc

**Files:**
- Create: `skills/lifecycle-hook-contracts/references/protocol-contracts.md`
- Create: `tests/test_lifecycle_hook_contracts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `references/protocol-contracts.md` (the verified per-runtime
  contract table every later task's adapters and audit checks implement);
  the test file's `GitFixture` base class, reused by every later task
  (`setUp` creates a temp git repo at `self.repo`, a `write(relative,
  content, executable=False)` helper that writes+`git add`s a file); the
  `run(*args, cwd, check=True, env=None)` subprocess helper; path constants
  `ROOT`, `SKILL_ROOT`, `ASSETS`, `RUNNER`, `AUDIT`.

- [ ] **Step 1: Write the reference doc**

```markdown
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
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_lifecycle_hook_contracts.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "lifecycle-hook-contracts"
ASSETS = SKILL_ROOT / "assets"
AUDIT = SKILL_ROOT / "scripts" / "audit.py"
RUNNER = ROOT / "skills" / "token-efficient-gates" / "assets" / "token-gate.sh"


def run(
    *args: str,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="lifecycle hook contracts ")
        self.repo = Path(self.tempdir.name) / "repo with spaces"
        self.repo.mkdir()
        run("git", "init", "-q", cwd=self.repo)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str, executable: bool = False) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        run("git", "add", relative, cwd=self.repo)
        return path


class ProtocolContractsDocTests(unittest.TestCase):
    def test_cites_both_verified_sources_and_marks_approve_invalid(self) -> None:
        content = (SKILL_ROOT / "references" / "protocol-contracts.md").read_text(encoding="utf-8")
        self.assertIn("code.claude.com/docs/en/hooks", content)
        self.assertIn("learn.chatgpt.com/docs/hooks", content)
        self.assertIn('"approve"', content)
        self.assertIn("antigravity.google/docs/hooks", content)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts -v`
Expected: FAIL — `FileNotFoundError` on `protocol-contracts.md` (doesn't
exist yet until Step 1 is on disk; if Step 1 was already done, this instead
checks content and should already PASS — if so, skip to Step 5).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts -v`
Expected: `Ran 1 test ... OK`

- [ ] **Step 5: Commit**

```bash
git add skills/lifecycle-hook-contracts/references/protocol-contracts.md tests/test_lifecycle_hook_contracts.py
git commit -m "docs: add Stop hook protocol contracts reference"
```

---

## Task 2: Claude Code Stop adapter

**Files:**
- Create: `skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-claude.sh`
- Create: `skills/lifecycle-hook-contracts/assets/lifecycle-hook.conf`
- Modify: `tests/test_lifecycle_hook_contracts.py` (append `ClaudeAdapterTests`)

**Interfaces:**
- Consumes: `token_gate_capture` from `skills/token-efficient-gates/assets/token-gate.sh`
  (sourced, unmodified) — exits 0 on PASS/WARN, nonzero on FAIL; its
  diagnostic summary line goes to stdout, which the adapter captures via
  command substitution and never forwards on success.
- Produces: `.claude/hooks/stop.sh` (installed path) implementing the
  contract from Task 1: exit 0 + stdout `{}` / exit 2 + stderr diagnostic.
  `scripts/lifecycle-hook.conf` (installed path) as a repo-editable,
  presence-only config that may set `STOP_HOOK_CMD` (default
  `pnpm verify:static`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle_hook_contracts.py` (after
`ProtocolContractsDocTests`):

```python
class ClaudeAdapterTests(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.runtime_tmp = (Path(self.tempdir.name) / "runtime tmp").resolve()
        self.runtime_tmp.mkdir(mode=0o700)
        self.write("scripts/token-gate.sh", RUNNER.read_text(encoding="utf-8"), executable=True)
        self.adapter = self.write(
            ".claude/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-claude.sh").read_text(encoding="utf-8"),
            executable=True,
        )

    def runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["TMPDIR"] = str(self.runtime_tmp)
        return env

    def configure(self, stop_hook_cmd: str) -> None:
        self.write("scripts/lifecycle-hook.conf", f"STOP_HOOK_CMD={shlex.quote(stop_hook_cmd)}\n")

    def run_adapter(self) -> subprocess.CompletedProcess[str]:
        return run("bash", str(self.adapter), cwd=self.repo, check=False, env=self.runtime_env())

    def test_passing_validation_yields_the_allow_stop_contract(self) -> None:
        self.configure("exit 0")
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "{}\n")
        self.assertEqual(result.stderr, "")

    def test_failing_validation_yields_the_keep_working_contract(self) -> None:
        self.configure("echo trouble; exit 1")
        result = self.run_adapter()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("FAIL", result.stderr)
        self.assertNotIn("trouble", result.stderr)

    def test_default_validation_command_is_verify_static(self) -> None:
        content = self.adapter.read_text(encoding="utf-8")
        self.assertIn('STOP_HOOK_CMD="pnpm verify:static"', content)

    def test_signal_killed_validation_terminates_the_adapter_via_the_same_signal(self) -> None:
        # Verified behavior, not a designed contract: token_gate_capture
        # re-raises a signal that killed the wrapped command by signaling
        # its own process (`kill -"$signal" "$$"`). Inside our `$(...)`
        # capture, `$$` still names the adapter script's own PID (bash
        # keeps `$$` pointing at the top-level shell inside command
        # substitutions), so the adapter is torn down by that same signal
        # before it ever reaches the `status=$?` line — it does NOT reach
        # the exit-2 branch. This is inherited, unmodified behavior from
        # `token-efficient-gates` (see Global Constraints — that engine is
        # never forked) and is intentionally not translated into the
        # exit-2 contract here; see "Explicitly out of scope" below.
        self.configure("kill -TERM $$")
        result = self.run_adapter()
        self.assertEqual(result.returncode, -15)
        self.assertEqual(result.stdout, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.ClaudeAdapterTests -v`
Expected: FAIL — `FileNotFoundError` (adapter script doesn't exist yet).

- [ ] **Step 3: Write the adapter script**

Create `skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-claude.sh`:

```bash
#!/usr/bin/env bash
# lifecycle-hook-contracts: canonical .claude/hooks/stop.sh v1 — do not
# hand-edit in the target repository; change the copy in sleeptimegrt-skills
# and re-apply.
#
# Claude Code Stop hook adapter — see references/protocol-contracts.md for
# the verified contract this implements: exit 0 + stdout `{}` lets the turn
# end; exit 2 + a stderr diagnostic asks Claude Code to keep working.
#
# `set -e` is intentionally omitted: `status=$?` below reads the exit code
# of a failing `token_gate_capture` call, and under `errexit` a nonzero
# command-substitution assignment exits the shell before that line runs.
set -uo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'lifecycle-hook-contracts: not inside a Git worktree\n' >&2
  exit 2
}

STOP_HOOK_CMD="pnpm verify:static"
# shellcheck source=/dev/null
[ -f "$REPO_ROOT/scripts/lifecycle-hook.conf" ] && . "$REPO_ROOT/scripts/lifecycle-hook.conf"

# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/token-gate.sh"

gate_output=$(cd "$REPO_ROOT" && token_gate_capture stop -- sh -c "$STOP_HOOK_CMD")
status=$?

if [ "$status" -eq 0 ]; then
  printf '{}\n'
  exit 0
fi

printf '%s\n' "$gate_output" >&2
exit 2
```

Make it executable: `chmod +x skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-claude.sh`

- [ ] **Step 4: Write the repo-editable config template**

Create `skills/lifecycle-hook-contracts/assets/lifecycle-hook.conf`:

```sh
# lifecycle-hook-contracts: repo-editable Stop hook config. NOT canonical
# (presence-only, like scripts/premerge.conf.sh or .githooks/pre-push.conf).
# Uncomment to override the default validation command.
# STOP_HOOK_CMD="pnpm verify:static"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.ClaudeAdapterTests -v`
Expected: `Ran 4 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-claude.sh \
        skills/lifecycle-hook-contracts/assets/lifecycle-hook.conf \
        tests/test_lifecycle_hook_contracts.py
git commit -m "feat: add Claude Code Stop hook adapter"
```

---

## Task 3: Codex Stop adapter

**Files:**
- Create: `skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-codex.sh`
- Modify: `tests/test_lifecycle_hook_contracts.py` (append `CodexAdapterTests`)

**Interfaces:**
- Consumes: same `token_gate_capture` contract as Task 2.
- Produces: `.codex/hooks/stop.sh` (installed path), same response contract
  as the Claude adapter. Kept as a separate canonical file (not a symlink or
  shared script) so it hash-audits and evolves independently per the design
  spec's rationale — today its body is identical to Task 2's.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle_hook_contracts.py` (after `ClaudeAdapterTests`):

```python
class CodexAdapterTests(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.runtime_tmp = (Path(self.tempdir.name) / "runtime tmp").resolve()
        self.runtime_tmp.mkdir(mode=0o700)
        self.write("scripts/token-gate.sh", RUNNER.read_text(encoding="utf-8"), executable=True)
        self.adapter = self.write(
            ".codex/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-codex.sh").read_text(encoding="utf-8"),
            executable=True,
        )

    def runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["TMPDIR"] = str(self.runtime_tmp)
        return env

    def configure(self, stop_hook_cmd: str) -> None:
        self.write("scripts/lifecycle-hook.conf", f"STOP_HOOK_CMD={shlex.quote(stop_hook_cmd)}\n")

    def run_adapter(self) -> subprocess.CompletedProcess[str]:
        return run("bash", str(self.adapter), cwd=self.repo, check=False, env=self.runtime_env())

    def test_passing_validation_yields_the_allow_stop_contract(self) -> None:
        self.configure("exit 0")
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "{}\n")
        self.assertEqual(result.stderr, "")

    def test_failing_validation_yields_the_keep_working_contract(self) -> None:
        self.configure("echo trouble; exit 1")
        result = self.run_adapter()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("FAIL", result.stderr)
        self.assertNotIn("trouble", result.stderr)

    def test_signal_killed_validation_terminates_the_adapter_via_the_same_signal(self) -> None:
        # See the identical test in ClaudeAdapterTests for why: this is
        # inherited token-gate.sh behavior, not a designed part of either
        # runtime's contract.
        self.configure("kill -TERM $$")
        result = self.run_adapter()
        self.assertEqual(result.returncode, -15)
        self.assertEqual(result.stdout, "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.CodexAdapterTests -v`
Expected: FAIL — `FileNotFoundError` (adapter script doesn't exist yet).

- [ ] **Step 3: Write the adapter script**

Create `skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-codex.sh`:

```bash
#!/usr/bin/env bash
# lifecycle-hook-contracts: canonical .codex/hooks/stop.sh v1 — do not
# hand-edit in the target repository; change the copy in sleeptimegrt-skills
# and re-apply.
#
# Codex Stop hook adapter — see references/protocol-contracts.md for the
# verified contract this implements: exit 0 + stdout `{}` lets the turn
# end; exit 2 + a stderr diagnostic asks Codex to keep working (documented
# explicitly as an alternative to the JSON decision path).
#
# `set -e` is intentionally omitted: `status=$?` below reads the exit code
# of a failing `token_gate_capture` call, and under `errexit` a nonzero
# command-substitution assignment exits the shell before that line runs.
set -uo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'lifecycle-hook-contracts: not inside a Git worktree\n' >&2
  exit 2
}

STOP_HOOK_CMD="pnpm verify:static"
# shellcheck source=/dev/null
[ -f "$REPO_ROOT/scripts/lifecycle-hook.conf" ] && . "$REPO_ROOT/scripts/lifecycle-hook.conf"

# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/token-gate.sh"

gate_output=$(cd "$REPO_ROOT" && token_gate_capture stop -- sh -c "$STOP_HOOK_CMD")
status=$?

if [ "$status" -eq 0 ]; then
  printf '{}\n'
  exit 0
fi

printf '%s\n' "$gate_output" >&2
exit 2
```

Make it executable: `chmod +x skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-codex.sh`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.CodexAdapterTests -v`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-codex.sh tests/test_lifecycle_hook_contracts.py
git commit -m "feat: add Codex Stop hook adapter"
```

---

## Task 4: cwd-independence tests for both adapters

**Files:**
- Modify: `tests/test_lifecycle_hook_contracts.py` (append `AdapterCwdIndependenceTests`)

**Interfaces:**
- Consumes: both canonical adapter files from Tasks 2 and 3.
- Produces: test coverage only — verifies the acceptance criterion that
  Stop hooks work identically when the session cwd is the repo root, a
  nested subdirectory, or a linked worktree whose path contains spaces (the
  literal condition that produced the original "No such file or directory"
  report in issue #1).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle_hook_contracts.py` (after `CodexAdapterTests`):

```python
class AdapterCwdIndependenceTests(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.write("scripts/token-gate.sh", RUNNER.read_text(encoding="utf-8"), executable=True)
        self.claude_adapter = self.write(
            ".claude/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-claude.sh").read_text(encoding="utf-8"),
            executable=True,
        )
        self.codex_adapter = self.write(
            ".codex/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-codex.sh").read_text(encoding="utf-8"),
            executable=True,
        )
        self.write("scripts/lifecycle-hook.conf", "STOP_HOOK_CMD='exit 0'\n")
        run("git", "config", "user.email", "fixture@example.test", cwd=self.repo)
        run("git", "config", "user.name", "Fixture", cwd=self.repo)
        run("git", "commit", "-qm", "fixture", cwd=self.repo)

    def test_adapters_resolve_repo_root_from_a_nested_directory(self) -> None:
        nested = self.repo / "packages" / "app"
        nested.mkdir(parents=True)
        for adapter in (self.claude_adapter, self.codex_adapter):
            result = run("bash", str(adapter), cwd=nested, check=False)
            self.assertEqual(result.returncode, 0, msg=str(adapter))
            self.assertEqual(result.stdout, "{}\n", msg=str(adapter))

    def test_adapters_resolve_repo_root_from_a_worktree_with_spaces(self) -> None:
        linked = Path(self.tempdir.name) / "linked worktree"
        run("git", "worktree", "add", "-q", "-b", "linked", str(linked), cwd=self.repo)
        for relative in (".claude/hooks/stop.sh", ".codex/hooks/stop.sh"):
            result = run("bash", str(linked / relative), cwd=linked, check=False)
            self.assertEqual(result.returncode, 0, msg=relative)
            self.assertEqual(result.stdout, "{}\n", msg=relative)
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.AdapterCwdIndependenceTests -v`

Both adapters already exist from Tasks 2–3, so this may already pass
(the cwd-resolution logic — `git rev-parse --show-toplevel` — was written
in Task 2/3, this task only adds the explicit regression coverage). If it
already passes, that's expected; proceed to Step 3 to confirm, not to
implement anything new.

- [ ] **Step 3: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.AdapterCwdIndependenceTests -v`
Expected: `Ran 2 tests ... OK`

- [ ] **Step 4: Commit**

```bash
git add tests/test_lifecycle_hook_contracts.py
git commit -m "test: cover Stop adapters from nested dir and worktree with spaces"
```

---

## Task 5: Audit — cross-runtime shared script and unsupported decision value

**Files:**
- Create: `skills/lifecycle-hook-contracts/scripts/audit.py`
- Modify: `tests/test_lifecycle_hook_contracts.py` (append `AuditSharedScriptTests`)

**Interfaces:**
- Consumes: `.claude/settings.json` / `.codex/hooks.json` in a target repo
  (read-only).
- Produces: `check_repo(repo: Path) -> list[dict]`, each dict shaped
  `{"check": str, "status": "PASS"|"FAIL"|"WARN"|"MISSING"|"INFO", "detail": str}`.
  Also `find_stop_commands(data: Any) -> list[str]` and
  `script_paths(commands: list[str]) -> set[str]`, both reused unchanged by
  Task 6. CLI: `python3 audit.py --repo <target> [--format json|text]`,
  exit 0 when compliant, 1 when FAIL/DRIFT findings exist, 2 on a
  usage/environment error (mirrors `harness-conventions/scripts/audit.py`'s
  shape).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle_hook_contracts.py` (after
`AdapterCwdIndependenceTests`):

```python
class AuditSharedScriptTests(GitFixture):
    def write_configs(self, claude_command: str | None, codex_command: str | None) -> None:
        if claude_command is not None:
            self.write(
                ".claude/settings.json",
                json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": claude_command}]}]}}),
            )
        if codex_command is not None:
            self.write(
                ".codex/hooks.json",
                json.dumps({"Stop": [{"hooks": [{"type": "command", "command": codex_command}]}]}),
            )

    def run_audit(self) -> dict:
        result = run("python3", str(AUDIT), "--repo", str(self.repo), "--format", "json", cwd=self.repo, check=False)
        return json.loads(result.stdout)

    def test_reproduces_the_original_approve_decision_bug(self) -> None:
        self.write(
            ".claude/hooks/lint-check.sh",
            """
            #!/usr/bin/env bash
            echo '{"decision":"approve"}'
            exit 0
            """,
            executable=True,
        )
        self.write_configs(
            claude_command="bash .claude/hooks/lint-check.sh",
            codex_command="bash .claude/hooks/lint-check.sh",
        )
        report = self.run_audit()
        self.assertFalse(report["compliant"])
        checks = [(item["check"], item["status"], item["detail"]) for item in report["results"]]
        self.assertTrue(any(check == "cross-runtime-script" and status == "FAIL" for check, status, _ in checks))
        self.assertTrue(
            any(
                check in ("claude:decision", "codex:decision") and status == "FAIL" and "approve" in detail
                for check, status, detail in checks
            )
        )

    def test_separate_per_runtime_scripts_do_not_trigger_shared_script_fail(self) -> None:
        self.write(".claude/hooks/stop.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
        self.write(".codex/hooks/stop.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
        self.write_configs(
            claude_command="bash .claude/hooks/stop.sh",
            codex_command="bash .codex/hooks/stop.sh",
        )
        report = self.run_audit()
        self.assertFalse(any(item["check"] == "cross-runtime-script" for item in report["results"]))

    def test_no_stop_hook_registered_is_informational(self) -> None:
        report = self.run_audit()
        self.assertTrue(report["compliant"])
        self.assertEqual({item["status"] for item in report["results"]}, {"INFO"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.AuditSharedScriptTests -v`
Expected: FAIL — `audit.py` doesn't exist yet.

- [ ] **Step 3: Write the audit script**

Create `skills/lifecycle-hook-contracts/scripts/audit.py`:

```python
#!/usr/bin/env python3
"""Read-only drift/compatibility audit for Stop hook lifecycle contracts.

Compares a target repository's .claude/settings.json and .codex/hooks.json
Stop hook registrations for the original bug class: a script shared
verbatim across both runtime configs, or one that emits an unsupported
`decision` value. Never modifies the target.

Usage:
    python3 audit.py --repo /path/to/repo [--format text|json]

Exit code 0 = compliant (INFO allowed), 1 = FAIL findings, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_TOKEN_RE = re.compile(r"([^\s\"']+\.(?:sh|py))")
DECISION_RE = re.compile(r'"decision"\s*:\s*"([^"]*)"')

FAILING = {"FAIL", "DRIFT"}


def find_stop_commands(data: Any) -> list[str]:
    """Collect every "command" string nested under any "Stop" key.

    Neither runtime's settings-file schema was fully confirmed during
    design (see references/protocol-contracts.md) — walking the tree for
    any "Stop" key, rather than asserting one exact nesting shape, keeps
    this working across the schema variants seen in each runtime's docs.
    """
    commands: list[str] = []

    def walk_commands(node: Any) -> None:
        if isinstance(node, dict):
            command = node.get("command")
            if isinstance(command, str):
                commands.append(command)
            for value in node.values():
                walk_commands(value)
        elif isinstance(node, list):
            for item in node:
                walk_commands(item)

    def find_stop(node: Any) -> None:
        if isinstance(node, dict):
            if "Stop" in node:
                walk_commands(node["Stop"])
            for value in node.values():
                find_stop(value)
        elif isinstance(node, list):
            for item in node:
                find_stop(item)

    find_stop(data)
    return commands


def script_paths(commands: list[str]) -> set[str]:
    paths: set[str] = set()
    for command in commands:
        for match in SCRIPT_TOKEN_RE.finditer(command):
            paths.add(match.group(1).strip("\"'"))
    return paths


def load_hook_config(repo: Path, relative: str, results: list[dict]) -> Any:
    path = repo / relative
    if not path.is_file():
        results.append({"check": relative, "status": "INFO", "detail": "not present"})
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        results.append({"check": relative, "status": "FAIL", "detail": f"invalid JSON: {exc}"})
        return None


def check_repo(repo: Path) -> list[dict]:
    results: list[dict] = []

    def add(check: str, status: str, detail: str) -> None:
        results.append({"check": check, "status": status, "detail": detail})

    claude_data = load_hook_config(repo, ".claude/settings.json", results)
    codex_data = load_hook_config(repo, ".codex/hooks.json", results)
    claude_commands = find_stop_commands(claude_data) if claude_data is not None else []
    codex_commands = find_stop_commands(codex_data) if codex_data is not None else []

    if not claude_commands and not codex_commands:
        add("stop-hook", "INFO", "no Stop hook registered in either runtime config")
        return results

    claude_paths = script_paths(claude_commands)
    codex_paths = script_paths(codex_commands)

    shared = claude_paths & codex_paths
    if shared:
        add(
            "cross-runtime-script",
            "FAIL",
            f"same script registered for both runtimes without per-runtime adapters: {sorted(shared)}",
        )

    for runtime, commands, paths in (
        ("claude", claude_commands, claude_paths),
        ("codex", codex_commands, codex_paths),
    ):
        if not commands:
            continue
        for path in paths:
            installed = repo / path
            if not installed.is_file():
                add(f"{runtime}:script", "MISSING", f"{path} referenced but not found")
                continue
            content = installed.read_text(encoding="utf-8", errors="replace")
            for match in DECISION_RE.finditer(content):
                value = match.group(1)
                if value != "block":
                    add(
                        f"{runtime}:decision",
                        "FAIL",
                        f"{path} emits unsupported decision value {value!r} (only \"block\" is valid)",
                    )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="path to the target repository")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"audit: {repo} is not a git repository", file=sys.stderr)
        return 2

    results = check_repo(repo)
    failed = [r for r in results if r["status"] in FAILING]

    if args.format == "json":
        print(json.dumps({"repo": str(repo), "compliant": not failed, "results": results}, indent=2))
    else:
        width = max((len(r["check"]) for r in results), default=0)
        for r in results:
            print(f"[{r['status']:>7}] {r['check']:<{width}}  {r['detail']}")
        verdict = "COMPLIANT" if not failed else f"DRIFT — {len(failed)} failing check(s)"
        print(f"\n{repo.name}: {verdict}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.AuditSharedScriptTests -v`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add skills/lifecycle-hook-contracts/scripts/audit.py tests/test_lifecycle_hook_contracts.py
git commit -m "feat: audit shared Stop scripts and unsupported decision values"
```

---

## Task 6: Audit — cwd-relative entrypoints, canonical-hash drift, mixed signaling

**Files:**
- Modify: `skills/lifecycle-hook-contracts/scripts/audit.py` (full rewrite —
  supersedes Task 5's version; every Task 5 test must still pass unchanged)
- Modify: `tests/test_lifecycle_hook_contracts.py` (append
  `AuditEntrypointAndDriftTests`)

**Interfaces:**
- Consumes: the canonical adapter files from Tasks 2 and 3 (for hash
  comparison — this is why this task must come after those two).
- Produces: `check_repo` gains three more finding categories per runtime —
  `{runtime}:entrypoint` (FAIL), `{runtime}:canonical-hash` (PASS/DRIFT),
  `{runtime}:signaling` (WARN) — using the same `check`-naming scheme
  Task 5 already established (`{runtime}:decision`, `{runtime}:script`,
  `cross-runtime-script`, `stop-hook`), so none of Task 5's assertions on
  those names change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle_hook_contracts.py` (after
`AuditSharedScriptTests`):

```python
class AuditEntrypointAndDriftTests(GitFixture):
    def write_claude_config(self, command: str) -> None:
        self.write(
            ".claude/settings.json",
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}),
        )

    def run_audit(self) -> dict:
        result = run("python3", str(AUDIT), "--repo", str(self.repo), "--format", "json", cwd=self.repo, check=False)
        return json.loads(result.stdout)

    def test_flags_cwd_relative_command_without_a_project_root_marker(self) -> None:
        self.write(".claude/hooks/stop.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
        self.write_claude_config("bash .claude/hooks/stop.sh")
        report = self.run_audit()
        self.assertTrue(
            any(item["check"] == "claude:entrypoint" and item["status"] == "FAIL" for item in report["results"])
        )

    def test_project_root_marker_satisfies_the_entrypoint_check(self) -> None:
        self.write(".claude/hooks/stop.sh", "#!/usr/bin/env bash\nexit 0\n", executable=True)
        self.write_claude_config("bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh")
        report = self.run_audit()
        self.assertFalse(any(item["check"] == "claude:entrypoint" for item in report["results"]))

    def test_flags_canonical_adapter_drift(self) -> None:
        self.write(".claude/hooks/stop.sh", "#!/usr/bin/env bash\necho tampered\nexit 0\n", executable=True)
        self.write_claude_config("bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh")
        report = self.run_audit()
        self.assertTrue(
            any(item["check"] == "claude:canonical-hash" and item["status"] == "DRIFT" for item in report["results"])
        )

    def test_matches_canonical_adapter_hash(self) -> None:
        self.write(
            ".claude/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-claude.sh").read_text(encoding="utf-8"),
            executable=True,
        )
        self.write_claude_config("bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh")
        report = self.run_audit()
        self.assertTrue(
            any(item["check"] == "claude:canonical-hash" and item["status"] == "PASS" for item in report["results"])
        )

    def test_flags_mixed_json_and_nonstandard_exit_code(self) -> None:
        self.write(
            ".claude/hooks/stop.sh",
            """
            #!/usr/bin/env bash
            echo '{"decision":"block","reason":"x"}'
            exit 1
            """,
            executable=True,
        )
        self.write_claude_config("bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh")
        report = self.run_audit()
        self.assertTrue(
            any(item["check"] == "claude:signaling" and item["status"] == "WARN" for item in report["results"])
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts.AuditEntrypointAndDriftTests -v`
Expected: FAIL — these finding categories don't exist in Task 5's version.

- [ ] **Step 3: Rewrite the audit script**

Replace the entire contents of
`skills/lifecycle-hook-contracts/scripts/audit.py` with:

```python
#!/usr/bin/env python3
"""Read-only drift/compatibility audit for Stop hook lifecycle contracts.

Compares a target repository's .claude/settings.json and .codex/hooks.json
Stop hook registrations against the canonical adapters bundled with this
skill. Never modifies the target.

Usage:
    python3 audit.py --repo /path/to/repo [--format text|json]

Exit code 0 = compliant (INFO/WARN allowed), 1 = FAIL/DRIFT findings,
2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"

CANONICAL = {
    ".claude/hooks/stop.sh": ASSETS / "hooks" / "stop-adapter-claude.sh",
    ".codex/hooks/stop.sh": ASSETS / "hooks" / "stop-adapter-codex.sh",
}

PROJECT_DIR_MARKERS = ("${CLAUDE_PROJECT_DIR}", "$(git rev-parse --show-toplevel)")
SCRIPT_TOKEN_RE = re.compile(r"([^\s\"']+\.(?:sh|py))")
DECISION_RE = re.compile(r'"decision"\s*:\s*"([^"]*)"')
EXIT_CODE_RE = re.compile(r"\bexit\s+(\d+)\b")

FAILING = {"FAIL", "DRIFT"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_stop_commands(data: Any) -> list[str]:
    """Collect every "command" string nested under any "Stop" key.

    Neither runtime's settings-file schema was fully confirmed during
    design (see references/protocol-contracts.md) — walking the tree for
    any "Stop" key, rather than asserting one exact nesting shape, keeps
    this working across the schema variants seen in each runtime's docs.
    """
    commands: list[str] = []

    def walk_commands(node: Any) -> None:
        if isinstance(node, dict):
            command = node.get("command")
            if isinstance(command, str):
                commands.append(command)
            for value in node.values():
                walk_commands(value)
        elif isinstance(node, list):
            for item in node:
                walk_commands(item)

    def find_stop(node: Any) -> None:
        if isinstance(node, dict):
            if "Stop" in node:
                walk_commands(node["Stop"])
            for value in node.values():
                find_stop(value)
        elif isinstance(node, list):
            for item in node:
                find_stop(item)

    find_stop(data)
    return commands


def script_paths(commands: list[str]) -> set[str]:
    # Marker prefixes are stripped from the whole command string before
    # tokenizing, not from the extracted token afterward: the Codex-style
    # marker `$(git rev-parse --show-toplevel)` contains internal spaces,
    # which would otherwise split it across the token boundary.
    paths: set[str] = set()
    for command in commands:
        stripped = command
        for marker in PROJECT_DIR_MARKERS:
            stripped = stripped.replace(marker + "/", "")
        for match in SCRIPT_TOKEN_RE.finditer(stripped):
            paths.add(match.group(1).strip("\"'"))
    return paths


def load_hook_config(repo: Path, relative: str, results: list[dict]) -> Any:
    path = repo / relative
    if not path.is_file():
        results.append({"check": relative, "status": "INFO", "detail": "not present"})
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        results.append({"check": relative, "status": "FAIL", "detail": f"invalid JSON: {exc}"})
        return None


def check_repo(repo: Path) -> list[dict]:
    results: list[dict] = []

    def add(check: str, status: str, detail: str) -> None:
        results.append({"check": check, "status": status, "detail": detail})

    claude_data = load_hook_config(repo, ".claude/settings.json", results)
    codex_data = load_hook_config(repo, ".codex/hooks.json", results)
    claude_commands = find_stop_commands(claude_data) if claude_data is not None else []
    codex_commands = find_stop_commands(codex_data) if codex_data is not None else []

    if not claude_commands and not codex_commands:
        add("stop-hook", "INFO", "no Stop hook registered in either runtime config")
        return results

    claude_paths = script_paths(claude_commands)
    codex_paths = script_paths(codex_commands)

    shared = claude_paths & codex_paths
    if shared:
        add(
            "cross-runtime-script",
            "FAIL",
            f"same script registered for both runtimes without per-runtime adapters: {sorted(shared)}",
        )

    for runtime, commands, paths, canonical_rel in (
        ("claude", claude_commands, claude_paths, ".claude/hooks/stop.sh"),
        ("codex", codex_commands, codex_paths, ".codex/hooks/stop.sh"),
    ):
        if not commands:
            continue

        for command in commands:
            if not any(marker in command for marker in PROJECT_DIR_MARKERS):
                add(f"{runtime}:entrypoint", "FAIL", f"cwd-relative command, not rooted: {command!r}")

        for path in paths:
            installed = repo / path
            if not installed.is_file():
                add(f"{runtime}:script", "MISSING", f"{path} referenced but not found")
                continue
            content = installed.read_text(encoding="utf-8", errors="replace")

            for match in DECISION_RE.finditer(content):
                value = match.group(1)
                if value != "block":
                    add(
                        f"{runtime}:decision",
                        "FAIL",
                        f"{path} emits unsupported decision value {value!r} (only \"block\" is valid)",
                    )

            exit_codes = {int(code) for code in EXIT_CODE_RE.findall(content)}
            if "decision" in content and exit_codes - {0, 2}:
                add(
                    f"{runtime}:signaling",
                    "WARN",
                    f"{path} mixes JSON decision output with exit code(s) {sorted(exit_codes - {0, 2})}",
                )

            if path == canonical_rel:
                canonical_asset = CANONICAL[canonical_rel]
                if sha256(installed) == sha256(canonical_asset):
                    add(f"{runtime}:canonical-hash", "PASS", "matches canonical adapter")
                else:
                    add(f"{runtime}:canonical-hash", "DRIFT", "differs from canonical adapter — re-apply or upstream")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="path to the target repository")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"audit: {repo} is not a git repository", file=sys.stderr)
        return 2

    results = check_repo(repo)
    failed = [r for r in results if r["status"] in FAILING]

    if args.format == "json":
        print(json.dumps({"repo": str(repo), "compliant": not failed, "results": results}, indent=2))
    else:
        width = max((len(r["check"]) for r in results), default=0)
        for r in results:
            print(f"[{r['status']:>7}] {r['check']:<{width}}  {r['detail']}")
        verdict = "COMPLIANT" if not failed else f"DRIFT — {len(failed)} failing check(s)"
        print(f"\n{repo.name}: {verdict}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts -v`
Expected: every test across all six test classes so far passes, including
Task 5's `AuditSharedScriptTests` unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/lifecycle-hook-contracts/scripts/audit.py tests/test_lifecycle_hook_contracts.py
git commit -m "feat: audit cwd-relative entrypoints, canonical drift, mixed signaling"
```

---

## Task 7: Skill entry point (SKILL.md)

**Files:**
- Create: `skills/lifecycle-hook-contracts/SKILL.md`

**Interfaces:**
- Consumes: every file path and behavior from Tasks 1–6 (documents them
  accurately — this is why it's last).
- Produces: the skill's discoverable entry point, following this repo's
  established frontmatter convention (`name` + `description` only, trigger
  conditions folded into `description`).

Before writing, check whether a `skill-creator` skill is available (per
this repo's `AGENTS.md` "Fresh agent protocol": *"For skill creation or
substantial skill changes, use the available skill-creator guidance before
editing"*). If one is listed among your available skills, invoke it and
follow its guidance instead of the template below where they differ. If
none is available, follow `AGENTS.md`'s own "Skill rules" section (already
reflected in the template below) and proceed.

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: lifecycle-hook-contracts
description: 'Cross-runtime contract, canonical adapters, and drift audit for agent lifecycle hooks shared between Claude Code and Codex, starting with the Stop hook. Use whenever a repo wires the same or related script into both .claude/settings.json and .codex/hooks.json, when a Stop hook reports invalid JSON output or fails after a cwd change, or before hand-editing .claude/hooks/stop.sh or .codex/hooks.json in a repository that follows this convention. Excludes Git-native hooks (harness-conventions), output-volume compaction (token-efficient-gates), and remote CI (remote-ci-economics).'
---

# Lifecycle Hook Contracts

One Stop-hook protocol, two runtimes. Each runtime's actual contract is
verified against its own official docs in
[references/protocol-contracts.md](references/protocol-contracts.md) — read
it before changing either adapter, since the two runtimes' rules differ in
ways that are easy to get wrong from memory (see the `"decision":"approve"`
regression this skill exists to catch).

## The contract

| Outcome | Response |
|---|---|
| Allow stop | exit 0, stdout `{}` |
| Keep working | exit 2, human-readable diagnostic on stderr |

Both `assets/hooks/stop-adapter-claude.sh` and
`assets/hooks/stop-adapter-codex.sh` implement exactly this, wrapping the
repo's existing `scripts/token-gate.sh` (from `token-efficient-gates`,
installed by `harness-conventions`) unmodified. Neither adapter emits a
`decision` field — no runtime-specific JSON schema is needed for the
Stop-only scope this skill covers.

**Dependency**: the target repo must already have `harness-conventions`
applied (`scripts/token-gate.sh` and a `verify:static` package script must
exist). This skill does not ship its own copy of the capture engine.

## Audit a repository

```bash
python3 <skill-dir>/scripts/audit.py --repo <target> [--format json]
```

Read-only. Flags: a script shared verbatim across both runtime configs
without per-runtime adapters, an unsupported `decision` value (e.g.
`"approve"`), a cwd-relative command with no `${CLAUDE_PROJECT_DIR}` or
`$(git rev-parse --show-toplevel)` rooting, drift against the canonical
adapter hash, and JSON output mixed with an exit code outside `{0, 2}`.

## Apply to a repository (only on explicit request)

Audit first; apply only when the user asks. One repository per commit.

1. Copy `assets/hooks/stop-adapter-claude.sh` → `<repo>/.claude/hooks/stop.sh`,
   `assets/hooks/stop-adapter-codex.sh` → `<repo>/.codex/hooks/stop.sh`. Mark
   both executable.
2. Point `.claude/settings.json`'s Stop hook at
   `${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh`, and `.codex/hooks.json`'s
   Stop hook at `$(git rev-parse --show-toplevel)/.codex/hooks/stop.sh` — not
   at the previous shared script directly.
3. If the repo's Stop validation needs something other than
   `pnpm verify:static`, copy `assets/lifecycle-hook.conf` to
   `<repo>/scripts/lifecycle-hook.conf` and set `STOP_HOOK_CMD`.
4. Run `audit.py` — it must exit COMPLIANT. Trigger a real Stop in each
   runtime once to confirm no "invalid hook output" warning appears.

## Boundaries

- **harness-conventions** owns Git-native hooks (pre-commit/pre-push/premerge)
  only; it does not gain a lifecycle-hook asset. This skill owns agent
  lifecycle hooks — Stop today, other events only if a real need appears.
- **token-efficient-gates** owns `scripts/token-gate.sh`; this skill wraps it
  unmodified via command substitution and never forks it.
- Antigravity has a third, distinct Stop contract (`decision: "continue"`,
  no documented exit-2 escape hatch) and is not covered — see
  `references/protocol-contracts.md`.
```

- [ ] **Step 2: Verify the audit and adapter paths referenced in SKILL.md actually exist**

Run:
```bash
test -x skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-claude.sh && echo OK
test -x skills/lifecycle-hook-contracts/assets/hooks/stop-adapter-codex.sh && echo OK
test -f skills/lifecycle-hook-contracts/assets/lifecycle-hook.conf && echo OK
test -f skills/lifecycle-hook-contracts/scripts/audit.py && echo OK
test -f skills/lifecycle-hook-contracts/references/protocol-contracts.md && echo OK
```
Expected: five lines of `OK`.

- [ ] **Step 3: Run the full test suite one last time**

Run: `python3 -m unittest tests.test_lifecycle_hook_contracts -v`
Expected: all tests across all seven test classes pass.

- [ ] **Step 4: Commit**

```bash
git add skills/lifecycle-hook-contracts/SKILL.md
git commit -m "docs: add lifecycle-hook-contracts SKILL.md"
```

---

## Explicitly out of scope for this plan

- Applying any of this to Medicount or any other product repository.
- A third (Antigravity) adapter.
- Any lifecycle hook other than Stop.
- Modifying `harness-conventions` or `token-efficient-gates`.
- Translating a signal-killed validation command into the exit-2 contract.
  Verified in Task 2/3: when the wrapped validation command dies to a
  signal, `token_gate_capture` re-raises that same signal against its own
  process, which — inside the adapter's `$(...)` capture — kills the
  adapter script itself before it reaches the exit-2 branch. The visible
  result is the raw signal death (e.g. return code `-15` for SIGTERM), not
  a clean exit 2. This is unmodified `token-efficient-gates` behavior (see
  Global Constraints); overriding it would mean forking that engine, which
  this plan does not do. If this proves to matter operationally against a
  real runtime, it's a follow-up issue, not a silent gap — it is now tested
  and documented rather than unspecified.

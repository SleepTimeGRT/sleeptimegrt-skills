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

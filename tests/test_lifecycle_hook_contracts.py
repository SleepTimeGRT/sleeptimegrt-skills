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
RUNNER = ROOT / "skills" / "lifecycle-gate-policy" / "assets" / "scripts" / "token-gate.sh"


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


class AuditEndToEndBothRuntimesTests(GitFixture):
    def install_both_adapters(self) -> None:
        self.write("scripts/token-gate.sh", RUNNER.read_text(encoding="utf-8"), executable=True)
        self.write(
            ".claude/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-claude.sh").read_text(encoding="utf-8"),
            executable=True,
        )
        self.write(
            ".codex/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-codex.sh").read_text(encoding="utf-8"),
            executable=True,
        )

    def write_configs(self) -> None:
        self.write(
            ".claude/settings.json",
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/stop.sh",
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
        )
        self.write(
            ".codex/hooks.json",
            json.dumps(
                {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "bash $(git rev-parse --show-toplevel)/.codex/hooks/stop.sh",
                                }
                            ]
                        }
                    ]
                }
            ),
        )

    def run_audit(self) -> dict:
        result = run("python3", str(AUDIT), "--repo", str(self.repo), "--format", "json", cwd=self.repo, check=False)
        return json.loads(result.stdout)

    def test_compliant_install_with_both_runtime_project_root_markers_passes_both_canonical_hash_checks(
        self,
    ) -> None:
        self.install_both_adapters()
        self.write_configs()
        report = self.run_audit()
        self.assertTrue(report["compliant"])
        checks = {(item["check"], item["status"]) for item in report["results"]}
        self.assertIn(("claude:canonical-hash", "PASS"), checks)
        self.assertIn(("codex:canonical-hash", "PASS"), checks)

    def test_tampered_codex_adapter_is_flagged_as_drift_alongside_a_compliant_claude_adapter(self) -> None:
        self.install_both_adapters()
        self.write_configs()
        self.write(
            ".codex/hooks/stop.sh",
            (ASSETS / "hooks" / "stop-adapter-codex.sh").read_text(encoding="utf-8") + "# tampered\n",
            executable=True,
        )
        report = self.run_audit()
        self.assertFalse(report["compliant"])
        checks = {(item["check"], item["status"]) for item in report["results"]}
        self.assertIn(("codex:canonical-hash", "DRIFT"), checks)

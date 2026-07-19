from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "skills" / "token-efficient-gates" / "scripts" / "audit.py"
MEASURE = ROOT / "skills" / "token-efficient-gates" / "scripts" / "measure.py"
RUNNER = ROOT / "skills" / "token-efficient-gates" / "assets" / "token-gate.sh"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="token efficient gates ")
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


class AuditTests(GitFixture):
    def test_inventory_classifies_local_gate_surfaces(self) -> None:
        self.write(
            "package.json",
            """
            {
                "scripts": {
                  "verify": "pnpm typecheck && ./tools/check.sh",
                  "verify:seeded": "pnpm typecheck && pnpm seed:test",
                  "dev": "next dev",
                  "deploy": "wrangler deploy",
                  "db:reset": "supabase db reset",
                  "e2e": "playwright test --project=e2e-password-reset",
                  "lint:fix": "biome check --write ."
                }
            }
            """,
        )
        self.write(".githooks/pre-push", "#!/usr/bin/env bash\npnpm verify\n", True)
        self.write("tools/check.sh", "#!/usr/bin/env bash\npnpm test:unit\n", True)
        self.write(
            "tools/e2e-ci.sh",
            "#!/usr/bin/env bash\n# local developers may use pnpm dev\npnpm --filter @fixture/web test:e2e\n",
            True,
        )
        self.write(
            ".github/workflows/verify.yml",
            """
            name: verify
            on:
              schedule:
                - cron: '0 * * * *'
            jobs:
              test:
                strategy:
                  matrix:
                    shard: [1, 2, 3]
                steps:
                  # pnpm comment-only must not become a call edge
                  - name: pnpm fake-label
                    run: pnpm --filter @fixture/web test:e2e
                  - run: pnpm test:pgtap
                  - uses: actions/upload-artifact@v4
              reusable:
                uses: ./.github/workflows/zz-reusable.yml
            """,
        )
        self.write(
            ".github/workflows/zz-reusable.yml",
            """
            on:
              workflow_call:
            jobs:
              test:
                timeout-minutes: 10
                steps:
                  - run: pnpm test:unit
            """,
        )
        before = run("git", "status", "--porcelain=v1", cwd=self.repo).stdout

        result = run("python3", str(AUDIT), "--repo", str(self.repo), "--format", "json", cwd=self.repo)
        report = json.loads(result.stdout)

        scripts = {(item["name"], item["classification"]) for item in report["package_scripts"]}
        self.assertIn(("verify", "gate"), scripts)
        self.assertIn(("e2e", "gate"), scripts)
        self.assertIn(("dev", "interactive"), scripts)
        self.assertIn(("deploy", "release-deploy"), scripts)
        self.assertIn(("db:reset", "destructive-data"), scripts)
        self.assertEqual(report["hooks"][0]["path"], ".githooks/pre-push")
        self.assertIn("tools/check.sh", report["shell_files"])
        shell_entries = {(item["path"], item["classification"]) for item in report["shell_entries"]}
        self.assertIn(("tools/check.sh", "gate"), shell_entries)
        self.assertIn(("tools/e2e-ci.sh", "gate"), shell_entries)
        package_entries = {item["name"]: item for item in report["package_scripts"]}
        self.assertIn("data-write-or-reset", package_entries["verify:seeded"]["safety_signals"])
        self.assertIn("mutates-worktree", package_entries["lint:fix"]["safety_signals"])

        edges = {(edge["source"], edge["target"]) for edge in report["call_edges"]}
        self.assertIn(("package.json#verify", "package:typecheck"), edges)
        self.assertIn(("package.json#verify", "tools/check.sh"), edges)
        self.assertIn((".githooks/pre-push", "package:verify"), edges)
        self.assertIn(("tools/check.sh", "package:test:unit"), edges)
        self.assertFalse(any(target == "package:--filter" for _, target in edges))
        self.assertFalse(any(source.startswith(".github/workflows/") for source, _ in edges))
        self.assertNotIn("workflows", report)
        self.assertNotIn("ci_review_signals", report.get("economics", {}))

        after = run("git", "status", "--porcelain=v1", cwd=self.repo).stdout
        self.assertEqual(after, before)

        text_result = run("python3", str(AUDIT), "--repo", str(self.repo), "--format", "text", cwd=self.repo)
        self.assertLessEqual(len(text_result.stdout.splitlines()), 10)
        self.assertIn("gate candidates:", text_result.stdout)
        self.assertIn("risk boundaries:", text_result.stdout)
        self.assertNotIn("ci review", text_result.stdout.lower())
        self.assertNotIn("package.json#dev", text_result.stdout)
        self.assertNotIn("package.json#deploy", text_result.stdout)


class RunnerTests(GitFixture):
    def run_gate(self, body: str) -> subprocess.CompletedProcess[str]:
        script = self.write(
            "run-gate.sh",
            f"""
            #!/usr/bin/env bash
            set -u
            source {json.dumps(str(RUNNER))}
            token_gate_begin verify
            {body}
            token_gate_finish
            """,
            True,
        )
        return run("bash", str(script), cwd=self.repo, check=False)

    def test_runner_compacts_pass_warn_and_fail_while_preserving_diagnostics(self) -> None:
        result = self.run_gate(
            """
            token_gate_stage pass -- bash -c 'echo many; echo lines'
            token_gate_stage --warn-regex 'deprecated' vocab -- bash -c 'echo deprecated >&2'
            token_gate_stage broken -- bash -c 'echo failure detail >&2; exit 23'
            exit $?
            """
        )

        self.assertEqual(result.returncode, 23)
        self.assertNotIn("many", result.stdout)
        self.assertNotIn("failure detail", result.stdout)
        self.assertRegex(result.stdout, r"\[verify\] PASS pass \([0-9.]+s\)")
        self.assertRegex(result.stdout, r"\[verify\] WARN vocab \([0-9.]+s\) — log: .+")
        self.assertRegex(result.stdout, r"\[verify\] FAIL broken \(exit 23, [0-9.]+s\) — log: .+")

        fail_line = next(line for line in result.stdout.splitlines() if "FAIL broken" in line)
        log_path = Path(fail_line.split(" — log: ", 1)[1])
        self.assertTrue(log_path.is_file())
        self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("many", log)
        self.assertIn("deprecated", log)
        self.assertIn("failure detail", log)
        self.assertEqual(run("git", "status", "--porcelain=v1", cwd=self.repo).stdout.count("token-gates"), 0)

    def test_runner_overwrites_stale_content(self) -> None:
        first = self.run_gate("token_gate_stage first -- bash -c 'echo stale-marker'")
        first_log = Path(next(line for line in first.stdout.splitlines() if "log:" in line).split("log: ", 1)[1])
        second = self.run_gate("token_gate_stage second -- bash -c 'echo fresh-marker'")
        second_log = Path(next(line for line in second.stdout.splitlines() if "log:" in line).split("log: ", 1)[1])

        self.assertEqual(first_log, second_log)
        content = second_log.read_text(encoding="utf-8")
        self.assertNotIn("stale-marker", content)
        self.assertIn("fresh-marker", content)

    def test_runner_preserves_signal_termination(self) -> None:
        result = self.run_gate("token_gate_stage signaled -- bash -c 'kill -TERM $$'")

        self.assertEqual(result.returncode, -15)
        self.assertRegex(result.stdout, r"\[verify\] FAIL signaled \(signal (?:TERM|15), [0-9.]+s\) — log: .+")

    def test_runner_reports_skip_as_a_distinct_outcome(self) -> None:
        result = self.run_gate("token_gate_skip integration 'database is unavailable'")

        self.assertEqual(result.returncode, 0)
        self.assertIn("[verify] SKIP integration — database is unavailable", result.stdout)
        self.assertIn("[verify] WARN 1 stages", result.stdout)

    def test_runner_accumulates_failure_when_the_caller_continues(self) -> None:
        result = self.run_gate(
            """
            token_gate_stage broken -- bash -c 'echo broken-detail; exit 7' || true
            token_gate_stage later -- bash -c 'echo later-detail'
            """
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[verify] FAIL broken (exit 7", result.stdout)
        self.assertIn("[verify] PASS later", result.stdout)
        self.assertIn("[verify] FAIL 2 stages", result.stdout)

    def test_runner_isolates_logs_between_linked_worktrees(self) -> None:
        self.write("tracked.txt", "fixture\n")
        run("git", "config", "user.email", "fixture@example.test", cwd=self.repo)
        run("git", "config", "user.name", "Fixture", cwd=self.repo)
        run("git", "commit", "-qm", "fixture", cwd=self.repo)
        linked = Path(self.tempdir.name) / "linked worktree"
        run("git", "worktree", "add", "-q", "-b", "linked", str(linked), cwd=self.repo)

        main_result = self.run_gate("token_gate_stage main -- bash -c 'echo main-marker'")
        linked_script = linked / "linked-gate.sh"
        linked_script.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                source {json.dumps(str(RUNNER))}
                token_gate_begin verify
                token_gate_stage linked -- bash -c 'echo linked-marker'
                token_gate_finish
                """
            ).lstrip(),
            encoding="utf-8",
        )
        linked_result = run("bash", str(linked_script), cwd=linked, check=False)

        main_log = Path(next(line for line in main_result.stdout.splitlines() if "log:" in line).split("log: ", 1)[1])
        linked_log = Path(next(line for line in linked_result.stdout.splitlines() if "log:" in line).split("log: ", 1)[1])
        self.assertNotEqual(main_log, linked_log)
        self.assertIn("main-marker", main_log.read_text(encoding="utf-8"))
        self.assertIn("linked-marker", linked_log.read_text(encoding="utf-8"))


class MeasureTests(GitFixture):
    def test_measure_keeps_noisy_output_out_of_terminal_and_preserves_failure_code(self) -> None:
        before = run("git", "status", "--porcelain=v1", cwd=self.repo).stdout
        result = run(
            "python3",
            str(MEASURE),
            "--repo",
            str(self.repo),
            "--label",
            "unit tests",
            "--",
            "bash",
            "-c",
            "printf 'line-%s\\n' {1..100}; echo failure-detail >&2; exit 19",
            cwd=self.repo,
            check=False,
        )

        self.assertEqual(result.returncode, 19)
        self.assertNotIn("line-1", result.stdout)
        self.assertNotIn("failure-detail", result.stdout)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["outcome"], "FAIL")
        self.assertEqual(summary["exit_code"], 19)
        self.assertEqual(summary["output_lines"], 101)
        self.assertGreater(summary["output_bytes"], 700)
        log_path = Path(summary["log_path"])
        self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
        self.assertIn("line-100", log_path.read_text(encoding="utf-8"))
        after = run("git", "status", "--porcelain=v1", cwd=self.repo).stdout
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()

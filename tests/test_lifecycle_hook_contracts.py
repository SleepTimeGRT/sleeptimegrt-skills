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

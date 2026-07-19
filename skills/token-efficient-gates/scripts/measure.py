#!/usr/bin/env python3
"""Measure a verified-safe command without forwarding its output to agent context."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def log_path(repo: Path, label: str) -> Path:
    safe_label = re.sub(r"[^A-Za-z0-9._-]", "_", label)
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    raw = Path(git(root, "rev-parse", "--git-path", f"token-gates/measure/{safe_label}/latest.log"))
    return raw if raw.is_absolute() else root / raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git repository where the command runs")
    parser.add_argument("--label", required=True, help="Stable label for the measured command")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command and arguments after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    try:
        repo = Path(git(Path(args.repo), "rev-parse", "--show-toplevel")).resolve()
        path = log_path(repo, args.label)
        old_umask = os.umask(0o077)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("wb") as output:
                started = time.monotonic()
                completed = subprocess.run(command, cwd=repo, stdout=output, stderr=subprocess.STDOUT, check=False)
                duration = time.monotonic() - started
            path.chmod(0o600)
        finally:
            os.umask(old_umask)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"outcome": "ERROR", "error": str(exc)}, sort_keys=True))
        return 2

    with path.open("rb") as output:
        output_lines = sum(1 for _ in output)
    return_code = completed.returncode if completed.returncode >= 0 else 128 - completed.returncode
    summary = {
        "duration_seconds": round(duration, 3),
        "exit_code": return_code,
        "label": args.label,
        "log_path": str(path),
        "outcome": "PASS" if completed.returncode == 0 else "FAIL",
        "output_bytes": path.stat().st_size,
        "output_lines": output_lines,
    }
    print(json.dumps(summary, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

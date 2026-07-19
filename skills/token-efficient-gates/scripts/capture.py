#!/usr/bin/env python3
"""Run one command with agent-facing summaries and recoverable diagnostics."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


INDEX_LIMIT = 5
TAIL_LINES = 20
SNIPPET_LIMIT = 180
FAILURE_MARKER = re.compile(
    r"(?:\berror(?:\[[^]]+\])?\b|\bfatal\b|\bpanic\b|\bexception\b|"
    r"\bfailed\b|^not ok\b|(?:^|\s)[✗×]\s)",
    re.IGNORECASE,
)
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


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
    raw = Path(git(root, "rev-parse", "--git-path", f"token-gates/capture/{safe_label}/latest.log"))
    return raw if raw.is_absolute() else root / raw


def clean_snippet(raw: str) -> str:
    cleaned = ANSI_ESCAPE.sub("", raw).replace("\r", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > SNIPPET_LIMIT:
        return f"{cleaned[: SNIPPET_LIMIT - 1]}…"
    return cleaned


def indexed_lines(path: Path, marker: re.Pattern[str]) -> tuple[list[tuple[int, str]], int]:
    matches: list[tuple[int, str]] = []
    line_count = 0
    with path.open("r", encoding="utf-8", errors="replace") as output:
        for line_count, raw in enumerate(output, start=1):
            searchable = ANSI_ESCAPE.sub("", raw).replace("\r", " ")
            if len(matches) < INDEX_LIMIT and marker.search(searchable):
                matches.append((line_count, clean_snippet(searchable)))
    return matches, line_count


def print_index(label: str, path: Path, marker: re.Pattern[str]) -> None:
    matches, line_count = indexed_lines(path, marker)
    if matches:
        for line_number, snippet in matches:
            print(f"[{label}] INDEX L{line_number}: {snippet}")
        return
    start = max(1, line_count - TAIL_LINES + 1)
    print(f"[{label}] INDEX no high-confidence marker; inspect L{start}-L{line_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git repository where the command runs")
    parser.add_argument("--label", required=True, help="Stable label for the command")
    parser.add_argument(
        "--warn-regex",
        help="Narrow verified marker that turns exit-zero output into WARN",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command and arguments after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    label = args.label.replace("\r", " ").replace("\n", " ")
    try:
        warning_marker = re.compile(args.warn_regex) if args.warn_regex else None
    except re.error as exc:
        print(f"[{label}] ERROR invalid --warn-regex: {exc}")
        return 64

    try:
        repo = Path(git(Path(args.repo), "rev-parse", "--show-toplevel")).resolve()
        path = log_path(repo, args.label)
        old_umask = os.umask(0o077)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("wb") as output:
                started = time.monotonic()
                completed = subprocess.run(
                    command,
                    cwd=repo,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                duration = time.monotonic() - started
            path.chmod(0o600)
        finally:
            os.umask(old_umask)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[{label}] ERROR {exc}")
        return 2

    elapsed = f"{duration:.3f}s"
    if completed.returncode == 0:
        if warning_marker is None:
            print(f"[{label}] PASS ({elapsed})")
            return 0
        warning_matches, _ = indexed_lines(path, warning_marker)
        if not warning_matches:
            print(f"[{label}] PASS ({elapsed})")
            return 0
        print(f"[{label}] WARN ({elapsed}) — log: {path}")
        for line_number, snippet in warning_matches:
            print(f"[{label}] INDEX L{line_number}: {snippet}")
        return 0

    if completed.returncode < 0:
        signal_number = -completed.returncode
        signal_name = signal.Signals(signal_number).name.removeprefix("SIG")
        print(f"[{label}] FAIL (signal {signal_name}, {elapsed}) — log: {path}", flush=True)
        print_index(label, path, FAILURE_MARKER)
        sys.stdout.flush()
        os.kill(os.getpid(), signal_number)
        return 128 + signal_number

    print(f"[{label}] FAIL (exit {completed.returncode}, {elapsed}) — log: {path}")
    print_index(label, path, FAILURE_MARKER)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

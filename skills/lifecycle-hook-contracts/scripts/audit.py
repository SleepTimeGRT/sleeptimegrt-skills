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

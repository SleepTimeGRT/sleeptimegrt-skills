#!/usr/bin/env python3
"""Read-only inventory of local gate surfaces that can waste agent tokens."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


HOOK_NAMES = {
    "pre-commit",
    "pre-push",
    "pre-merge-commit",
    "commit-msg",
    "prepare-commit-msg",
    "post-commit",
    "post-merge",
    "post-checkout",
}

DESTRUCTIVE_NAME_RE = re.compile(r"(?:^|[:_./-])(reset|wipe|seed|truncate|drop|destroy|cleanup|rm)(?=$|[:_./-])", re.I)
RELEASE_NAME_RE = re.compile(r"(?:^|[:_./-])(deploy|release|publish|ship)(?=$|[:_./-])", re.I)
INTERACTIVE_NAME_RE = re.compile(r"(?:^|[:_./-])(dev|start|serve|watch|debug|headed|ui)(?=$|[:_./-])", re.I)
GATE_NAME_RE = re.compile(r"(?:^|[:_./-])(verify|check|lint|typecheck|test|ci|validate|audit|spec|e2e|build)(?=$|[:_./-])", re.I)

PACKAGE_CALL_RE = re.compile(
    r"\bpnpm(?:\s+--(?:filter|dir)(?:=|\s+)\S+|\s+--[A-Za-z0-9-]+)*\s+(?:run\s+)?([A-Za-z][A-Za-z0-9:_-]*)"
    r"|\b(?:npm\s+run\s+|yarn\s+(?:run\s+)?|bun\s+run\s+)([A-Za-z][A-Za-z0-9:_-]*)"
)
PACKAGE_BUILTINS = {"add", "config", "create", "dlx", "exec", "fetch", "import", "init", "install", "list", "remove", "store", "update"}

DATA_WRITE_RE = re.compile(
    r"\b(?:supabase\s+db\s+reset|(?:pnpm|yarn|bun(?:\s+run)?|npm\s+run)\s+(?:--[^\s]+\s+)*(?:seed|reset|wipe|drop|truncate)(?=[:\s]|$))",
    re.I,
)
WORKTREE_WRITE_RE = re.compile(r"(?:^|\s)(?:--write|--fix)(?:\s|$)|\brm\s+-[A-Za-z]*r[A-Za-z]*f?\b", re.I)
EXTERNAL_WRITE_RE = re.compile(r"\b(?:firebase|wrangler|vercel|npm|pnpm)\s+(?:[^&;]*\s)?(?:deploy|publish|release)\b", re.I)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def classify(name: str, command: str = "") -> tuple[str, list[str]]:
    checks = (
        ("destructive-data", DESTRUCTIVE_NAME_RE, "destructive/data entrypoint name"),
        ("release-deploy", RELEASE_NAME_RE, "release/deploy entrypoint name"),
        ("interactive", INTERACTIVE_NAME_RE, "interactive development entrypoint name"),
        ("gate", GATE_NAME_RE, "verification entrypoint name"),
    )
    for category, pattern, reason in checks:
        if pattern.search(name):
            return category, [reason]
    command_head_checks = (
        ("gate", r"^\s*(?:playwright|vitest|jest)\s+test\b|^\s*node\s+--test\b", "test command"),
        ("interactive", r"^\s*(?:next|vite)\s+dev\b", "interactive command"),
        ("release-deploy", r"^\s*(?:wrangler|firebase|vercel)\s+deploy\b", "deploy command"),
        ("destructive-data", r"^\s*supabase\s+db\s+reset\b", "destructive data command"),
    )
    for category, pattern, reason in command_head_checks:
        if re.search(pattern, command, re.I):
            return category, [reason]
    return "unclassified", ["manual review required"]


def safety_signals(command: str) -> list[str]:
    signals: list[str] = []
    if DATA_WRITE_RE.search(command):
        signals.append("data-write-or-reset")
    if WORKTREE_WRITE_RE.search(command):
        signals.append("mutates-worktree")
    if EXTERNAL_WRITE_RE.search(command):
        signals.append("external-write")
    return signals


def tracked_files(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return sorted(item.decode("utf-8", "surrogateescape") for item in result.stdout.split(b"\0") if item)


def read_tracked(repo: Path, relative: str, findings: list[dict[str, str]]) -> str | None:
    path = repo / relative
    if path.is_symlink():
        findings.append({"path": relative, "reason": "symlink skipped"})
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        findings.append({"path": relative, "reason": f"read failed: {exc.strerror or type(exc).__name__}"})
        return None


def call_edges(source: str, content: str, tracked: set[str]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    shell_files = [path for path in tracked if path.endswith(".sh")]
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or re.match(r"^(?:echo|printf)\b", stripped):
            continue
        for match in PACKAGE_CALL_RE.finditer(line):
            script_name = match.group(1) or match.group(2)
            if script_name in PACKAGE_BUILTINS:
                continue
            target = f"package:{script_name}"
            key = (source, target)
            if key not in seen:
                edges.append({"source": source, "target": target, "evidence": stripped[:240]})
                seen.add(key)
        for candidate in shell_files:
            if re.search(rf"(?<![A-Za-z0-9_./-])(?:\./)?{re.escape(candidate)}(?![A-Za-z0-9_./-])", line):
                key = (source, candidate)
                if key not in seen:
                    edges.append({"source": source, "target": candidate, "evidence": stripped[:240]})
                    seen.add(key)
    return edges


def audit(repo_arg: str) -> dict[str, Any]:
    repo = Path(git(Path(repo_arg), "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    tracked = tracked_files(repo)
    tracked_set = set(tracked)
    skipped: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    hooks: list[dict[str, Any]] = []
    shell_files = [path for path in tracked if path.endswith(".sh")]
    for path in tracked:
        if Path(path).name not in HOOK_NAMES:
            continue
        content = read_tracked(repo, path, skipped)
        if content is None:
            continue
        hooks.append({"path": path, "classification": "gate", "reason": "Git hook entry point"})
        edges.extend(call_edges(path, content, tracked_set))

    shell_entries: list[dict[str, Any]] = []
    for path in shell_files:
        if any(item["path"] == path for item in hooks):
            continue
        content = read_tracked(repo, path, skipped)
        if content is None:
            continue
        category, reasons = classify(path, content)
        shell_entries.append(
            {"path": path, "classification": category, "reasons": reasons, "safety_signals": safety_signals(content)}
        )
        edges.extend(call_edges(path, content, tracked_set))

    package_scripts: list[dict[str, Any]] = []
    for path in (item for item in tracked if Path(item).name == "package.json"):
        content = read_tracked(repo, path, skipped)
        if content is None:
            continue
        try:
            scripts = json.loads(content).get("scripts", {})
        except json.JSONDecodeError as exc:
            skipped.append({"path": path, "reason": f"invalid JSON at line {exc.lineno}"})
            continue
        if not isinstance(scripts, dict):
            continue
        for name, command in sorted(scripts.items()):
            if not isinstance(command, str):
                continue
            category, reasons = classify(name, command)
            source = f"{path}#{name}"
            package_scripts.append(
                {
                    "path": path,
                    "name": name,
                    "command": command,
                    "classification": category,
                    "reasons": reasons,
                    "safety_signals": safety_signals(command),
                }
            )
            edges.extend(call_edges(source, command, tracked_set))

    hooks_path_result = git(repo, "config", "--path", "--get", "core.hooksPath", check=False)
    classified_entries = [*shell_entries, *package_scripts]
    counts = Counter(item["classification"] for item in classified_entries)
    economics = {
        "gate_candidates": {"hooks": len(hooks), "shell_and_package": counts["gate"]},
        "risk_boundaries": {
            "interactive": counts["interactive"],
            "release-deploy": counts["release-deploy"],
            "destructive-data": counts["destructive-data"],
            "safety-signaled": sum(bool(item.get("safety_signals")) for item in classified_entries),
            "unclassified": counts["unclassified"],
        },
    }
    return {
        "schema_version": 1,
        "repo_root": str(repo),
        "configured_hooks_path": hooks_path_result.stdout.strip() or None,
        "hooks": hooks,
        "shell_files": shell_files,
        "shell_entries": shell_entries,
        "package_scripts": package_scripts,
        "call_edges": sorted(edges, key=lambda item: (item["source"], item["target"])),
        "skipped": skipped,
        "economics": economics,
        "summary": {
            "hooks": len(hooks),
            "shell_files": len(shell_files),
            "package_scripts": len(package_scripts),
            "call_edges": len(edges),
        },
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    economics = report["economics"]
    gates = economics["gate_candidates"]
    boundaries = economics["risk_boundaries"]
    lines = [
        f"token-efficient-gates audit: {report['repo_root']}",
        f"inventory: {summary['hooks']} hooks, {summary['shell_files']} shell files, {summary['package_scripts']} package scripts",
        (
            "gate candidates: "
            f"{gates['hooks']} hooks, {gates['shell_and_package']} shell/package; "
            f"{summary['call_edges']} direct call edges"
        ),
        "risk boundaries: " + ", ".join(f"{name}={count}" for name, count in boundaries.items()),
    ]
    lines.extend(f"[skip] {item['path']}: {item['reason']}" for item in report["skipped"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git repository to inspect")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        report = audit(args.repo)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"token-efficient-gates audit failed: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

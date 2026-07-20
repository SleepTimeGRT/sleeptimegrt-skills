#!/usr/bin/env python3
"""Read-only GitHub Actions economics evidence collector.

Gathers repository, run, job, storage, and (when readable) organization
billing evidence into one JSON bundle for analyze.py. Uses only GET requests
through `gh api`; never triggers, reruns, or cancels workflows and never
touches billing or settings. Unreachable endpoints become recorded errors in
the bundle instead of aborting the audit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from typing import Any


def gh_api(path: str) -> tuple[Any, str | None]:
    """Run `gh api <path>` and return (parsed JSON, error string)."""
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:  # gh missing or not executable
        return None, f"gh unavailable: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return None, f"GET {path} failed: {detail[0] if detail else 'unknown error'}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError:
        return None, f"GET {path} returned non-JSON"


def iso_seconds(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    try:
        start = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (end - start).total_seconds()


def month_iter(now: dt.date, months: int) -> list[tuple[int, int]]:
    out = []
    year, month = now.year, now.month
    for _ in range(months):
        out.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out


def collect(repo: str, months: int, max_runs: int, max_job_runs: int, max_annotations: int) -> dict[str, Any]:
    errors: list[str] = []

    def get(path: str) -> Any:
        data, err = gh_api(path)
        if err:
            errors.append(err)
        return data

    bundle: dict[str, Any] = {
        "schema": "remote-ci-economics/bundle@1",
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "repo": repo,
        "errors": errors,
    }

    meta = get(f"repos/{repo}")
    if meta is None:
        # Without repository metadata nothing else is meaningful.
        return bundle
    bundle["meta"] = {
        k: meta.get(k)
        for k in ("full_name", "private", "visibility", "default_branch", "created_at", "pushed_at")
    }
    owner = meta.get("owner") or {}
    bundle["meta"]["owner_login"] = owner.get("login")
    bundle["meta"]["owner_type"] = owner.get("type")

    workflows = get(f"repos/{repo}/actions/workflows")
    bundle["registered_workflows"] = [
        {"path": w.get("path"), "state": w.get("state")} for w in (workflows or {}).get("workflows", [])
    ]

    branch = bundle["meta"].get("default_branch") or "HEAD"
    tree = get(f"repos/{repo}/contents/.github/workflows?ref={branch}")
    bundle["default_branch_workflow_files"] = (
        [e.get("path") for e in tree] if isinstance(tree, list) else []
    )

    runs: list[dict[str, Any]] = []
    page = 1
    while len(runs) < max_runs:
        chunk = get(f"repos/{repo}/actions/runs?per_page=100&page={page}")
        if not chunk or not chunk.get("workflow_runs"):
            break
        if page == 1:
            bundle["total_run_count"] = chunk.get("total_count")
        for r in chunk["workflow_runs"]:
            runs.append(
                {
                    "id": r.get("id"),
                    "path": r.get("path"),
                    "event": r.get("event"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "run_attempt": r.get("run_attempt"),
                    "run_started_at": r.get("run_started_at"),
                    "updated_at": r.get("updated_at"),
                    "head_branch": r.get("head_branch"),
                    "head_sha": r.get("head_sha"),
                }
            )
        if len(chunk["workflow_runs"]) < 100:
            break
        page += 1
    bundle["runs"] = runs[:max_runs]

    jobs: list[dict[str, Any]] = []
    completed = [r for r in bundle["runs"] if r.get("status") == "completed"]
    for r in completed[:max_job_runs]:
        detail = get(f"repos/{repo}/actions/runs/{r['id']}/jobs")
        for j in (detail or {}).get("jobs", []):
            jobs.append(
                {
                    "run_id": r["id"],
                    "job_id": j.get("id"),
                    "name": j.get("name"),
                    "conclusion": j.get("conclusion"),
                    "labels": j.get("labels"),
                    "started_at": j.get("started_at"),
                    "completed_at": j.get("completed_at"),
                    "duration_s": iso_seconds(j.get("started_at"), j.get("completed_at")),
                    "steps_n": len(j.get("steps") or []),
                }
            )
    bundle["jobs"] = jobs

    # Annotations for jobs that died instantly with no steps: the failure
    # reason (billing block, runner refusal) lives only in the check run.
    suspicious = [
        j for j in jobs
        if j.get("conclusion") == "failure" and j.get("steps_n") == 0
        and j.get("duration_s") is not None and j["duration_s"] <= 10
    ]
    annotations = []
    for j in suspicious[:max_annotations]:
        ann = get(f"repos/{repo}/check-runs/{j['job_id']}/annotations")
        if isinstance(ann, list):
            annotations.append(
                {"job_id": j["job_id"], "run_id": j["run_id"], "messages": [a.get("message") for a in ann]}
            )
    bundle["instant_failure_annotations"] = annotations

    bundle["cache_usage"] = get(f"repos/{repo}/actions/cache/usage")
    caches = get(f"repos/{repo}/actions/caches?per_page=100")
    bundle["caches"] = (caches or {}).get("actions_caches", [])
    artifacts = get(f"repos/{repo}/actions/artifacts?per_page=100")
    bundle["artifacts"] = {
        "total_count": (artifacts or {}).get("total_count"),
        "items": [
            {
                "name": a.get("name"),
                "size_in_bytes": a.get("size_in_bytes"),
                "created_at": a.get("created_at"),
                "expires_at": a.get("expires_at"),
            }
            for a in (artifacts or {}).get("artifacts", [])
        ],
    }

    # Workflow file history explains steps in the spend series (added, grown,
    # deleted). Runs reveal paths that no longer exist on the default branch.
    paths = sorted({r.get("path") for r in bundle["runs"] if r.get("path")})
    history = {}
    for path in paths[:10]:
        commits = get(f"repos/{repo}/commits?path={path}&per_page=30")
        if isinstance(commits, list):
            history[path] = [
                {
                    "sha": (c.get("sha") or "")[:10],
                    "date": ((c.get("commit") or {}).get("committer") or {}).get("date"),
                    "message": ((c.get("commit") or {}).get("message") or "").splitlines()[0],
                }
                for c in commits
            ]
    bundle["workflow_history"] = history

    if bundle["meta"].get("owner_type") == "Organization":
        org = bundle["meta"]["owner_login"]
        today = dt.datetime.now(dt.timezone.utc).date()
        usage_by_month = {}
        for year, month in month_iter(today, months):
            usage = get(f"organizations/{org}/settings/billing/usage?year={year}&month={month}")
            usage_by_month[f"{year}-{month:02d}"] = (usage or {}).get("usageItems")
        bundle["billing"] = {
            "org": org,
            "usage_by_month": usage_by_month,
            "summary": get(
                f"organizations/{org}/settings/billing/usage/summary?year={today.year}&month={today.month}"
            ),
            "budgets": (get(f"organizations/{org}/settings/billing/budgets") or {}).get("budgets"),
        }
    else:
        bundle["billing"] = {
            "org": None,
            "note": "owner is not an organization; user-account billing needs the 'user' scope",
        }

    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--months", type=int, default=3, help="billing months to fetch (default 3)")
    parser.add_argument("--runs", type=int, default=200, help="max runs to sample (default 200)")
    parser.add_argument("--job-runs", type=int, default=30, help="completed runs to fetch jobs for (default 30)")
    parser.add_argument("--annotations", type=int, default=10, help="max instant-failure annotations (default 10)")
    parser.add_argument("--out", default="-", help="output file (default stdout)")
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print("error: gh CLI not found; the collector reads GitHub only through gh api", file=sys.stderr)
        return 2

    bundle = collect(args.repo, args.months, args.runs, args.job_runs, args.annotations)
    text = json.dumps(bundle, indent=1, ensure_ascii=False)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        summary = f"bundle: {args.out} ({len(bundle.get('runs', []))} runs, {len(bundle.get('jobs', []))} jobs, {len(bundle.get('errors', []))} errors)"
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

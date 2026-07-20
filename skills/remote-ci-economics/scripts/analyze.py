#!/usr/bin/env python3
"""Deterministic analysis of a collect.py evidence bundle.

Pure computation, no network: billable estimates via per-job minute round-up
and runner multipliers, spend split by workflow and job, event mix, rerun and
cancellation rates, billed monthly totals against the plan quota, burn
projection, billing-block detection, and inventory mismatches. Estimates are
always labeled as estimates; billed figures come only from the bundle's
billing section.

Reference values (prices, multipliers, quotas) mirror
references/github-actions-billing.md as fetched 2026-07-20; re-verify there
before presenting results as current.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from collections import Counter, defaultdict
from typing import Any

# Mirrors references/github-actions-billing.md (fetched 2026-07-20).
MULTIPLIERS = {"linux": 1, "windows": 2, "macos": 10}
PRICE_PER_MIN = {"linux": 0.006, "windows": 0.010, "macos": 0.062}
INCLUDED_MINUTES = {"free": 2000, "team": 3000, "enterprise": 50000}
BLOCK_RE = re.compile(r"job was not started because", re.I)


def runner_class(labels: list[str] | None) -> tuple[str, bool]:
    """Map job labels to a runner class; second value marks an assumption."""
    for label in labels or []:
        lower = label.lower()
        if "ubuntu" in lower or "linux" in lower:
            return "linux", False
        if "windows" in lower:
            return "windows", False
        if "macos" in lower or "mac-" in lower:
            return "macos", False
    return "linux", True


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def is_blocked_job(job: dict[str, Any]) -> bool:
    return (
        job.get("conclusion") == "failure"
        and job.get("steps_n") == 0
        and job.get("duration_s") is not None
        and job["duration_s"] <= 10
    )


def analyze(bundle: dict[str, Any], plan: str | None) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def finding(tag: str, text: str) -> None:
        findings.append({"tag": tag, "finding": text})

    runs = bundle.get("runs") or []
    jobs = bundle.get("jobs") or []

    # --- run sample -----------------------------------------------------
    event_mix = Counter((r.get("event"), r.get("conclusion")) for r in runs)
    reruns = sum(1 for r in runs if (r.get("run_attempt") or 1) > 1)
    cancelled = sum(1 for r in runs if r.get("conclusion") == "cancelled")
    started = [r["run_started_at"] for r in runs if r.get("run_started_at")]
    run_summary = {
        "sample_size": len(runs),
        "total_run_count": bundle.get("total_run_count"),
        "window": {"oldest": min(started, default=None), "newest": max(started, default=None)},
        "by_event_conclusion": {f"{e}/{c}": n for (e, c), n in sorted(event_mix.items())},
        "rerun_runs": reruns,
        "cancelled_runs": cancelled,
    }
    events = Counter(r.get("event") for r in runs)
    if events.get("push", 0) and events.get("pull_request", 0):
        share = events["push"] / len(runs)
        finding(
            "opportunity",
            f"push runs are {share:.0%} of the sample alongside pull_request runs — "
            "check for PR+push double verification of the same change",
        )

    # --- billable estimates (labeled estimates, per-job round-up) -------
    per_run_min: dict[Any, float] = defaultdict(float)
    per_job_stats: dict[str, list[float]] = defaultdict(list)
    assumed_runner = False
    for j in jobs:
        if j.get("duration_s") is None or is_blocked_job(j):
            continue
        cls, assumed = runner_class(j.get("labels"))
        assumed_runner = assumed_runner or assumed
        billed = math.ceil(j["duration_s"] / 60) * MULTIPLIERS[cls]
        per_run_min[j["run_id"]] += billed
        per_job_stats[j.get("name") or "?"].append(j["duration_s"])
    run_costs = list(per_run_min.values())
    estimates = {
        "note": "estimates from job timestamps (per-job minute round-up, quota multipliers); not observed billing",
        "runner_class_assumed_for_some_jobs": assumed_runner,
        "runs_estimated": len(run_costs),
        "billable_min_per_run_mean": round(sum(run_costs) / len(run_costs), 1) if run_costs else None,
        "billable_min_per_run_max": max(run_costs, default=None),
        "jobs": {
            name: {
                "n": len(durs),
                "p50_s": percentile(durs, 0.5),
                "max_s": max(durs),
                "billed_min_at_p50": math.ceil(percentile(durs, 0.5) / 60),
            }
            for name, durs in sorted(per_job_stats.items())
        },
    }
    for name, stat in estimates["jobs"].items():
        if stat["billed_min_at_p50"] >= 4:
            finding("opportunity", f"job '{name}' bills ~{stat['billed_min_at_p50']} min per run at p50 — top placement-review candidate")

    # --- billing-block detection ----------------------------------------
    blocked = [j for j in jobs if is_blocked_job(j)]
    annotation_hits = [
        a for a in bundle.get("instant_failure_annotations") or []
        if any(BLOCK_RE.search(m or "") for m in a.get("messages") or [])
    ]
    blocked_run_ids = {j["run_id"] for j in blocked}
    blocked_windows = sorted(
        r["run_started_at"] for r in runs if r.get("id") in blocked_run_ids and r.get("run_started_at")
    )
    block_summary = {
        "instant_dead_jobs": len(blocked),
        "annotation_confirmed": len(annotation_hits),
        "first_seen": blocked_windows[0] if blocked_windows else None,
        "last_seen": blocked_windows[-1] if blocked_windows else None,
    }
    if annotation_hits:
        finding(
            "confirmed",
            f"billing block: {len(annotation_hits)} annotation-confirmed refused jobs "
            f"between {block_summary['first_seen']} and {block_summary['last_seen']} — "
            "these runs verified nothing and billed nothing",
        )
    elif blocked:
        finding("risk", f"{len(blocked)} jobs died instantly with zero steps — fetch their annotations to confirm or rule out a billing block")

    # --- inventory mismatches -------------------------------------------
    run_paths = {r.get("path") for r in runs if r.get("path")}
    tracked = set(bundle.get("default_branch_workflow_files") or [])
    off_branch = sorted(p for p in run_paths if p not in tracked)
    if off_branch:
        finding(
            "risk",
            f"runs exist for workflow paths not on the default branch: {', '.join(off_branch)} — "
            "branch-only or deleted workflows still spend minutes",
        )

    # --- billed usage (authoritative) ------------------------------------
    billing = bundle.get("billing") or {}
    monthly: dict[str, Any] = {}
    for month_key, items in (billing.get("usage_by_month") or {}).items():
        if items is None:
            monthly[month_key] = "unknown (endpoint unreadable or no data)"
            continue
        by_sku: dict[str, float] = defaultdict(float)
        by_repo_equiv: dict[str, float] = defaultdict(float)
        gross = net = 0.0
        for item in items:
            gross += item.get("grossAmount") or 0
            net += item.get("netAmount") or 0
            if item.get("unitType") == "Minutes":
                sku = item.get("sku") or "?"
                qty = item.get("quantity") or 0
                # Rank repos by quota consumption, not raw minutes: one macOS
                # minute drains the included quota like ten Linux minutes.
                mult = (
                    MULTIPLIERS["macos"] if "macos" in sku.lower()
                    else MULTIPLIERS["windows"] if "windows" in sku.lower()
                    else 1
                )
                by_sku[sku] += qty
                by_repo_equiv[item.get("repositoryName") or "?"] += qty * mult
        monthly[month_key] = {
            "minutes_by_sku": dict(by_sku),
            "quota_minute_equivalents_by_repo": dict(sorted(by_repo_equiv.items(), key=lambda kv: -kv[1])),
            "quota_minute_equivalents": sum(by_repo_equiv.values()),
            "gross_amount": round(gross, 3),
            "net_amount": round(net, 3),
        }
        if net > 0:
            finding("confirmed", f"{month_key}: ${net:.2f} billed beyond the included quota")

    quota = INCLUDED_MINUTES.get(plan or "")
    projection: dict[str, Any] | None = None
    current = dt.datetime.now(dt.timezone.utc)
    current_key = f"{current.year}-{current.month:02d}"
    cur = monthly.get(current_key)
    if isinstance(cur, dict) and quota:
        used = cur["quota_minute_equivalents"]
        rate = used / max(current.day, 1)
        projection = {
            "note": "projection, not observed billing; assumes calendar-month cycle and steady burn",
            "plan": plan,
            "included_minutes": quota,
            "used_minute_equivalents": used,
            "used_pct": round(100 * used / quota, 1),
            "daily_rate_min": round(rate, 1),
            "est_days_to_exhaustion": round((quota - used) / rate, 1) if rate > 0 and used < quota else 0,
        }
        if used >= quota:
            finding("confirmed", f"{current_key}: included quota consumed ({used:.0f}/{quota} minute-equivalents) — expect org-wide blocks if overage is prevented")
        elif used / quota > 0.7:
            finding("risk", f"{current_key}: {projection['used_pct']}% of included quota consumed with ~{projection['est_days_to_exhaustion']} days of burn remaining")
    budgets = billing.get("budgets") or []
    for b in budgets:
        if b.get("budget_product_sku") == "actions" and b.get("budget_amount") == 0 and b.get("prevent_further_usage"):
            finding("risk", "actions budget is $0 with prevent_further_usage — quota exhaustion becomes a hard org-wide stop")

    if not runs and not bundle.get("registered_workflows"):
        finding("unknown", "no runs and no registered workflows observed — verify other CI providers before concluding zero remote spend")

    return {
        "schema": "remote-ci-economics/analysis@1",
        "observed_at": bundle.get("observed_at"),
        "repo": bundle.get("repo"),
        "collection_errors": bundle.get("errors") or [],
        "run_summary": run_summary,
        "billable_estimates": estimates,
        "billing_block": block_summary,
        "billed_monthly": monthly,
        "quota_projection": projection,
        "findings": findings,
    }


def to_markdown(a: dict[str, Any]) -> str:
    lines = [f"## Analysis — {a['repo']} (observed {a['observed_at']})", ""]
    for f in a["findings"]:
        lines.append(f"- **[{f['tag']}]** {f['finding']}")
    if not a["findings"]:
        lines.append("- no findings — candidate no-change result")
    lines += ["", "### Run sample", "```json", json.dumps(a["run_summary"], indent=1), "```"]
    lines += ["### Billable estimates (not observed billing)", "```json", json.dumps(a["billable_estimates"], indent=1), "```"]
    lines += ["### Billed monthly (authoritative where present)", "```json", json.dumps(a["billed_monthly"], indent=1), "```"]
    if a.get("quota_projection"):
        lines += ["### Quota projection", "```json", json.dumps(a["quota_projection"], indent=1), "```"]
    if a["collection_errors"]:
        lines += ["### Collection errors (report as unknowns)"] + [f"- {e}" for e in a["collection_errors"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, help="bundle JSON from collect.py")
    parser.add_argument("--plan", choices=sorted(INCLUDED_MINUTES), help="verified account plan; omit if unknown")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    args = parser.parse_args()

    with open(args.bundle, encoding="utf-8") as fh:
        bundle = json.load(fh)
    analysis = analyze(bundle, args.plan)
    print(to_markdown(analysis) if args.format == "md" else json.dumps(analysis, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

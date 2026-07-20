# GitHub Actions billing facts and APIs

Every number here was read from the linked primary source on the stated date.
Prices, quotas, and endpoints change: when the fetch date is more than a few
months old, or when a computation is about to be shown to a user as current,
re-fetch the source and update this file rather than quoting from memory.

## Pricing and multipliers (fetched 2026-07-20)

Source: <https://docs.github.com/en/billing/reference/actions-runner-pricing>

- Rounding: "GitHub rounds the minutes and partial minutes each job uses up to
  the nearest whole minute." Rounding is per job, not per run.
- Standard hosted runners, per-minute: Linux 2-core x64 $0.006 (arm64 $0.005,
  1-core $0.002), Windows 2-core $0.010, macOS 3–4-core $0.062.
- Larger runners are billed for public repositories too, up to $0.252/min
  (Linux 96-core) and $0.552/min (Windows 96-core).

Source: <https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions>

- Quota multipliers: Windows consumes included minutes at 2x, macOS at 10x.
- Included per month for private repositories: Free 2,000 min / Team 3,000 /
  Enterprise Cloud 50,000. Artifact storage included: 500 MB / 2 GB / 50 GB.
- Standard hosted runners on public repositories are free; self-hosted runners
  are free.
- Storage: artifacts $0.25/GB-month, cache overage $0.07/GB-month, both accrued
  hourly; cache allowance is 10 GB per repository.
- Quota exhaustion without a valid payment method blocks further usage.

Limits source: <https://docs.github.com/en/actions/reference/limits>
(fetched 2026-07-20): Free plan 20 concurrent jobs (5 macOS); job hard limit
6 h hosted; workflow run limit 35 days; 100 runs queued per concurrency group.

## Billing APIs (verified against live organizations 2026-07-20)

Source: <https://docs.github.com/en/rest/billing/usage>

- `GET /organizations/{org}/settings/billing/usage?year=Y&month=M` — usage
  items with `date`, `product`, `sku`, `quantity`, `unitType`, `pricePerUnit`,
  `grossAmount`, `discountAmount`, `netAmount`, `repositoryName`.
  `discountAmount == grossAmount` means the included quota absorbed the usage;
  `netAmount > 0` is real money. Data retention: 24 months.
  **Always pass `year` and `month`:** without parameters the endpoint returns
  aggregated rows whose `repositoryName` is misleading (observed: an org's
  whole monthly Linux total attributed to one repository).
- `GET /organizations/{org}/settings/billing/usage/summary` — per-SKU monthly
  totals (public preview on the fetch date).
- `GET /organizations/{org}/settings/billing/budgets` — budgets;
  `budget_amount: 0` with `prevent_further_usage: true` means a hard stop at
  quota exhaustion, persisting until the cycle resets or an admin intervenes.
- User-account equivalents exist under `/users/{username}/settings/billing/...`
  but require the `user` OAuth scope (observed 404 without it).
- The classic endpoint `GET /orgs/{org}/settings/billing/actions` is gone
  (observed HTTP 410 "This endpoint has been moved").
- Access: the docs require organization admin or billing manager. A token that
  can read these endpoints for one org may still fail for another — record the
  failure per org instead of generalizing.

## Run-level evidence APIs

- `GET /repos/{r}/actions/runs?per_page=100` — sample runs; `path` reveals
  workflows that exist only on branches or were deleted. `run_attempt > 1`
  marks reruns. `updated_at - run_started_at` is wall-clock, not billed time.
- `GET /repos/{r}/actions/runs/{id}/jobs` — per-job `started_at`/
  `completed_at`/`labels`/`steps`; the basis for round-up billable estimates.
- `GET /repos/{r}/check-runs/{job_id}/annotations` — failure reasons in
  machine-readable form, including the billing-block message.
- `GET /repos/{r}/actions/cache/usage`, `/actions/caches`, `/actions/artifacts`
  — storage-side evidence.
- `GET /repos/{r}/commits?path=.github/workflows/<file>` — when a workflow was
  added, reshaped, or deleted, which often explains spend steps in the usage
  series.

## Billing-block signature (observed live 2026-07-20)

All of the following together identify a run refused for billing reasons:

1. Job conclusion `failure` with `steps: []` and 2–4 s duration.
2. Job log request returns 404 (no blob was ever written).
3. Check-run annotation: "The job was not started because recent account
   payments have failed or your spending limit needs to be increased. Please
   check the 'Billing & plans' section in your settings".
4. The run bills nothing — usage reports stay flat while runs go red.

The block applies org-wide the moment quota exhausts mid-run-stream: earlier
runs the same evening bill normally, later ones die at start. A commit merged
during a block lands on the default branch unverified by CI — flag that
explicitly, since the run list makes it look merely "failed".

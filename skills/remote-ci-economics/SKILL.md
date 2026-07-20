---
name: remote-ci-economics
description: 'Audit and improve the economics of remote CI: GitHub Actions billed minutes, included quota and runner multipliers, duplicate PR/push runs, caches, artifacts, and the placement of gates between remote CI and the local development harness. Use whenever the user asks about CI cost, Actions minutes, quota exhaustion, billing blocks ("The job was not started"), slimming or deleting workflows, whether a gate such as E2E, emulator, or pgTAP belongs in CI or locally, or before adding or reshaping workflows in a private repository. The audit is read-only and never triggers workflow runs; repository changes happen only on explicit request. Excludes compaction of agent-facing terminal output, which belongs to token-efficient-gates.'
---

# Remote CI Economics

Reduce metered CI spend, not verification coverage. Every recommendation either
preserves existing coverage or names the exact coverage being traded away.

## Audit contract

The audit is observation only:

- Read state through GET requests (`gh api`). Never trigger, rerun, or cancel a
  workflow, and never change billing, budgets, spending limits, or repository
  settings to produce data.
- Every claim about external state carries its source and observation date.
  Data you could not read is reported as unknown — an unavailable billing field
  is a finding, not a blank to fill with a plausible number.
- Billed minutes come only from billing APIs. Numbers derived from job
  timestamps are estimates and must be labeled as such: GitHub bills each job's
  duration rounded up to the whole minute, so wall-clock arithmetic and real
  charges diverge — and runs refused at start bill nothing while still showing
  as failures.

## Establish the operating profile first

Confirm before judging anything, because identical workflows get opposite
verdicts under different profiles:

1. Account plan and repository visibility (private repositories consume metered
   quota; public standard runners do not).
2. Team size and device count.
3. Whether branch-protection required checks are available and used (on
   free-plan private repositories they typically are not — remote CI then has
   no merge-enforcement power).
4. What the local development harness already verifies, and whether development
   is agent-driven.

A solo developer on one device with an agent-run local harness has no other
consumer for remote run evidence and usually no merge enforcement; for that
profile the default posture is *cheap deterministic gates in CI at most, heavy
verification in the local harness* — and "no remote CI at all" is a legitimate
recommendation. A team relying on required checks may need the opposite. Never
assume the team-CI default.

## Collect evidence

```bash
python3 <skill-dir>/scripts/collect.py --repo <owner>/<name> --out bundle.json
```

The collector gathers, read-only and bounded: repository metadata, registered
workflows and the default-branch workflow files, a recent run sample, job and
step timings for a subsample, cache and artifact usage, workflow-file commit
history, failure annotations for instantly-dead jobs, and — when the owner is
an organization the credentials can read — billing usage, usage summary, and
budgets. Endpoints it cannot reach are recorded inside the bundle as errors.

Inventory pitfalls the collector exists to catch:

- **No workflow on the default branch does not mean no spend.** Pull-request
  runs execute the workflow file from the PR merge ref, so branch-only
  workflows bill real minutes; deleted workflows leave history and spend
  behind. The run sample's `path` set is the truth, not the workflows listing.
- **Months missing from an organization's usage report may mean the repository
  was billed to a different owner then** (for example before a transfer), not
  that nothing ran.
- **The usage endpoint aggregates misleadingly without parameters** — always
  query with explicit `year` and `month`, which the collector does.

## Analyze deterministically

```bash
python3 <skill-dir>/scripts/analyze.py --bundle bundle.json --plan free --format md
```

The analyzer computes, without network access: per-job and per-run billable
estimates (per-job minute round-up, runner multipliers), spend split by
workflow and by job, PR/push event mix and duplication, rerun and cancellation
rates, monthly billed totals against the plan's included quota with a burn
projection, and billing-block detection. Pass `--plan` only when the plan is
verified; omit it and quota context is reported unknown.

## Recognize billing blocks

A job refused for billing reasons looks like a test failure but is not one:
conclusion `failure`, zero steps, two-to-four-second duration, no log blob, and
a check-run annotation reading "The job was not started because recent account
payments have failed or your spending limit needs to be increased." Diagnose
this before debugging tests that never ran. Blocked runs bill nothing, so a
repository can show hundreds of red runs and near-zero metered usage; with a
zero budget and `prevent_further_usage`, the block persists until the monthly
quota resets or an administrator changes billing — both outside this audit's
authority to touch.

## Classify each gate for placement

Score every job by: billed minutes per run (each job rounds up separately),
trigger frequency, failure yield, feedback latency, local reproducibility, and
whether anyone other than the author consumes the remote evidence. Then place:

- **Remote CI**: cheap, deterministic, fast gates — and only what the profile
  justifies keeping remote.
- **Local harness**: heavy, locally reproducible verification (E2E, emulators,
  database/pgTAP suites, type-checks) when the profile has no remote
  enforcement or evidence consumer.
- **Scheduled or manual remote runs**: clean-environment checks that exist to
  catch local environment drift — these need occasional runs, not per-PR runs.

Recurring expensive shapes to check: the PR+push double run on the same change
(push-to-main re-verifies what the PR just verified); many small jobs each
rounding up a minute versus one merged job (cheaper, but blurs failure
attribution — name the trade-off); per-run browser or JDK installs whose real
step cost should be measured before recommending a cache (they are often
cheaper than assumed); generous timeouts on hang-prone jobs (the timeout is the
worst-case bill).

E2E and pgTAP are placed by this scoring, never removed categorically.

## Report format

Use exactly this structure:

```markdown
# Remote CI economics audit — <target> (<observation date>)
## 1. Current spend evidence
## 2. Expensive paths
## 3. Coverage and risk constraints
## 4. Ranked recommendations
## 5. Savings estimates
## 6. No-change findings
## 7. Unknowns and access limits
```

Tag findings `confirmed` / `risk` / `opportunity` / `unknown`. Savings
estimates show the formula, evidence window, sample size, and assumptions, and
are never presented as observed billing. "No optimization is justified" is a
valid and complete result. Constraints that survive optimization (required
checks that must keep their job-key context names, coverage the user has chosen
to keep) belong in section 3 so recommendations cannot silently violate them.

## Apply only on explicit request

The audit changes nothing. When the user separately requests changes: keep each
repository's changes in its own commit and PR, preserve required-check context
names (job keys are contracts with branch protection), preserve exit-code and
fail-fast semantics of anything moved, and restate the coverage trade-off in
the PR description so the decision stays reviewable.

## Reference

Read [references/github-actions-billing.md](references/github-actions-billing.md)
before quoting any price, quota, multiplier, or endpoint: it carries the
current verified values with fetch dates, the API access requirements, and
re-verification instructions. Prices and quotas are temporally unstable — a
stale number presented as current is a provenance failure.

# Handoff — harness-conventions drafted & fixture-tested; remote-ci-economics evals still pending

## harness-conventions (new skill, 2026-07-21) — draft complete, not committed, not applied

Cross-repo harness policy skill at `skills/harness-conventions/`. Decision record and all
user-confirmed choices are in `references/policy-rationale.md` and agent memory
`harness-unification-three-repos` (3-layer gates: pre-commit gitleaks+biome / static-only
pre-push / premerge = full verify + e2e + cross-model review for code PRs; self-merge
allowed on premerge PASS; gate-integrity paths mechanically PROTECTED; `.githooks` +
prepare, husky removed; naming contract verify / verify:static / premerge).

State:
- Canonical assets (`assets/githooks/*`, `assets/scripts/{premerge.sh,token-gate.sh}`) —
  token-gate.sh is the goldrush production copy + marker header; hooks/premerge are new.
  Canonical files are hash-audited; repo-editable configs (`premerge.conf.sh`,
  `worktree-links.conf`, `pre-push.conf`) are presence-checked only.
- `scripts/audit.py` read-only drift audit: fixture-tested (16/16 incl. spaces-in-path,
  PROTECTED, review-required, behind-main, dirty-tree, worktree symlinks, exit-code
  passthrough) via scratchpad `fixture-test.sh`; official `quick_validate.py` passed
  (via `uv run --with pyyaml`, cwd must be the skill-creator dir). Real-repo audits run
  clean and show expected pre-application drift (medicount 11, samhaengsi/goldrush 7).
- **medicount APPLIED (2026-07-21, user-approved)**: issue #221, PR #222
  (github.com/MediCount/MediCount/pull/222) — awaiting HUMAN merge (premerge correctly
  reports PROTECTED exit 3 on its own branch). husky removed; .githooks installed;
  verify:ci → verify (capture label renamed), stamp gate deleted
  (working-tree-hash.sh, .husky/, .git/verify-ci-stamp); verify:static + premerge wired
  (premerge.conf.sh: E2E_CMD="pnpm e2e", PROTECTED_EXTRA covers verify-ci.sh +
  guide/gate test files); gate tests rewritten (12/12; WARN case now exercises
  token-gate --warn-regex directly, since the stamp warn marker is gone);
  dev-workflow.md rewritten (guide-contract checker constraints: must mention ports
  3001/3002, no "CI auto-runs" phrasing); AGENTS.md got the policy section.
  All checks verified: verify:guides 12/12, verify:static + verify green,
  audit COMPLIANT, pre-commit/pre-push fired live, post-checkout symlinked 3 files.
  NOTE: `pnpm e2e` was NOT executed this session (needs local Supabase stack) — the
  first real premerge run will exercise it; if red/slow, tune premerge.conf.sh.
- **ALL THREE REPOS APPLIED (2026-07-21)**:
  - medicount #221 → PR #222 **MERGED** (main 0c2f9f1).
  - goldrush #508 → PR studio-hevv/toss-space-goldrush#509 awaiting human merge.
    pre-push lightened full-verify → verify:static; premerge E2E_CMD="pnpm test:e2e"
    (Playwright webServer self-starts emulator+web+seed); AGENTS.md self-merge policy
    now premerge-based (resolved its contradiction with pickup-issue); org refs
    SleepTimeGRT→studio-hevv fixed; test:token-gate green after marker header.
  - samhaengsi #618 → PR studio-hevv/toss-samhaengsi#619 awaiting human merge.
    tools/token-gate.sh → scripts/ (git mv); tools/pre-merge-local.sh DELETED,
    replaced by premerge.sh (E2E_CMD="pnpm test:e2e:ci"); pre-push dropped
    test:unit/test:tools (static only; spec:vocab WARN_REGEX via .githooks/
    pre-push.conf — confirmed WARN+index on live push); self-merge ban (#598
    incident) converted to premerge-based conditional self-merge; method-decision
    0006 got a 2026-07-21 amendment; spec-gardener ghost post-commit ref fixed;
    policy marker embedded inline in AGENTS.md merge-policy bullet (their
    "no config mirroring" doc culture — not the full template section).
  - All three: audit COMPLIANT, hooks fired live, premerge PROTECTED exit 3
    verified on the application branch itself. e2e suites NOT executed this
    session in any repo — first real code PR premerge will exercise them.
- NOT yet done: skill-creator eval loop (optional); this repo's own changes are
  uncommitted (user has not requested a commit). Superpowers skills are
  complemented, not replaced (AGENTS.md policy template supplies the declared
  preferences they ask about).
- Do not commit or push this repo unless the user explicitly asks.

---

# Prior handoff — remote-ci-economics: drafted; pilots applied; fixtures and evals next

## Pilot rollout status (applied 2026-07-20, user-approved)

All three pilots are now at **zero remote CI on main + a local pre-push gate**:

- **toss-space-goldrush**: PR
  [#501](https://github.com/studio-hevv/toss-space-goldrush/pull/501) squash-merged as
  `9da999fe7ce24967b4479997d421ad6cba4566b0`. Deleted `.github/workflows/verify.yml`
  (verify + e2e, PR+push); wired `.githooks/pre-push` to run `pnpm verify` through the
  token-efficient gate (`scripts/verify-agent.sh`). Local gate verified PASS (~37–51 s) and
  the hook fired live on push. Coverage trade-off: `verify` preserved (moved to blocking
  local pre-push); `e2e` moved from remote per-PR to local on-demand (`pnpm test:e2e`).
  Done in an isolated Orca worktree (now removed); remote branch deleted.
- **toss-samhaengsi**: already zero remote CI (workflow deleted by the team 7/18); has a
  token-gate `.githooks/pre-push`. No change needed — no PR.
- **medicount**: main has zero workflows; local gate via `.husky/pre-push`. No change
  needed — no PR.

Still outstanding and **outside this repo's authority** (org-admin UI only): studio-hevv
Actions remains billing-blocked until the Aug 1 quota reset or a billing change. goldrush
now has no remote CI to block, so this no longer gates goldrush merges.

## Current state (2026-07-20)

The second skill exists as a validated draft at `skills/remote-ci-economics/`:

- `SKILL.md` — audit contract (read-only, provenance-dated claims, unknowns stay unknown),
  operating-profile-first judgment, inventory pitfalls, billing-block signature, gate-placement
  classification, fixed 7-section report template, apply-only-on-explicit-request.
- `scripts/collect.py` — read-only evidence collector over `gh api` (runs, jobs, annotations,
  caches, artifacts, workflow history, org billing usage/summary/budgets). Endpoint failures are
  recorded inside the bundle, not fatal.
- `scripts/analyze.py` — network-free deterministic analyzer (per-job round-up billable
  estimates, runner multipliers, event mix, rerun/cancel rates, billed monthly totals,
  quota-equivalents by repo, burn projection, billing-block detection, tagged findings).
  Collection/analysis are split so fixture tests need only JSON bundles.
- `references/github-actions-billing.md` — prices, quotas, multipliers, limits, API endpoints and
  access requirements, each with source URL and fetch date (2026-07-20), plus re-verification
  instructions and the observed API quirks.

The official skill validator passed (`quick_validate.py`, run via `uv run --with pyyaml` because
system python lacks pyyaml). Smoke test against live `studio-hevv/toss-space-goldrush` reproduced
all five manual audit findings automatically.

Uncommitted working-tree changes: `skills/remote-ci-economics/` (new), one boundary line in
`skills/token-efficient-gates/SKILL.md` now naming `remote-ci-economics`, and this file. The user
has not requested a commit. Do not commit or push unless explicitly asked.

## Decisions confirmed with the user this session

1. Scope: GitHub Actions first-class; concepts and report provider-neutral. Name:
   `remote-ci-economics` (chosen after economics were understood, per prior instruction).
2. Contract: audit-and-recommend first; apply only on explicit request. Report =
   spend evidence → expensive paths → coverage/risk constraints → ranked recommendations →
   savings estimates (formula + assumptions) → no-change findings → unknowns/access limits.
3. Development philosophy (also saved to agent memory `ci-philosophy-light-remote-heavy-local`):
   the user's projects are almost all **solo-dev, single device, agent-driven**. Remote CI is
   "barely necessary"; keep at most cheap deterministic gates in CI, put heavy verification
   (E2E, emulators, pgTAP, type-checks) in the local harness. "No remote CI" is a legitimate
   recommendation for this profile. Never assume team-CI defaults. Residual risk is local
   environment drift → occasional clean-environment run (manual dispatch), not per-PR CI.
4. medicount was confirmed by the user to have been transferred from a personal repo to the
   MediCount org after a billing problem — this validated the audit's transfer inference.

## Verified audit evidence (2026-07-20, GitHub REST API, account SleepTimeGRT)

Full reports were written to session scratchpad `ci-audit/reports/` (ephemeral); the essentials:

### Corrections to the previous handoff's premises

"No tracked workflow" for medicount/samhaengsi was misleading. Pull-request runs execute the
workflow file from the PR merge ref, so branch-only workflows bill real minutes; both repos had
substantial spend. Run-sample `path`s, not the workflows listing, are the inventory truth.

### studio-hevv org (free plan, 2,000 included min/month; all repos private)

- July (through 7/19): Linux 1,420 min + macOS 57 min (10x multiplier) = **1,990/2,000
  quota-minute-equivalents, gross $12.054, net $0**. May 38, June 47 min — July exploded.
- By quota consumption: toss-samhaengsi 1,165 (58%), ultari 600 equiv (57 macOS min — 2nd
  biggest consumer), toss-space-goldrush 186, others ≤30.
- Budgets API: `actions` (and 3 other SKUs) budget **$0 + prevent_further_usage: true** → hard
  org-wide stop at quota exhaustion.
- **The org is BLOCKED since 2026-07-19 18:25–18:38 UTC** (last real goldrush job 18:25; from
  18:38 jobs die in 2–3 s, steps 0, log blob 404, annotation "The job was not started because
  recent account payments have failed or your spending limit needs to be increased"). The e2e
  stabilization commit `1cef906b` reached goldrush main **unverified by CI**. Block persists
  until Aug 1 reset or an org admin changes billing — user decision, outside audit authority.
- goldrush: verify job p50 98 s → 2 billed min; e2e p50 276 s → 5–6 billed min; runs without
  e2e ≈1.8, with e2e ≈6.5 min. PR+push double-run ≈43–45% push share. Biggest lever: drop e2e
  from push-to-main (PR-only). Playwright-install caching hypothesis was REFUTED by step
  measurement (~24 s install) — measure step costs before recommending caches.
- samhaengsi: 3-job CI (gate 91 s / emulator 202 s / e2e 168 s ≈ 9 billed min/run) burned
  1,165 min in 8 days (7/10–7/18); the team deleted the workflow from main 7/18 12:12
  (`bd81f4ee` "chore(ci): GitHub Actions 제거 → 로컬 3층 검증 (free-private 비용)"). Under the
  solo-dev profile this deletion is coherent, not overcorrection. Workflow comments confirm
  required checks are unavailable on free-private (403).
- medicount (MediCount org): July 20 min, June 29, Mar–May no usage items (billed to previous
  owner pre-transfer). Billing block observed 7/6–7/18 09:03 (same signature, annotation
  verified); normal from 7/18 09:19 ≈ transfer time. Current slim `ci.yml` (biome-check +
  path-filtered conditional jobs; e2e removed from GHA 7/3, heavy gates local via
  `pnpm verify:ci`) already matches the target posture — a genuine mostly-no-change case.

### Credential/access limits (record, do not re-derive)

- Token scopes `repo`, `read:org`: org billing usage/summary/budgets readable for BOTH orgs;
  user-account billing 404 (needs `user` scope); classic org billing endpoint HTTP 410.
- Usage endpoint without `year`/`month` params returns aggregation with misleading
  `repositoryName` — always pass both (collector does).

## Next-session plan

1. Read `AGENTS.md` and this file. The skill draft is done — do not redesign it from scratch.
2. Build temporary fixture bundles/repos per the archetypes below; add `tests/` for
   `analyze.py` (pure JSON-in) and collector arg/error paths.
3. Create realistic eval prompts; run with-skill and baseline evals per `skill-creator`
   (workspace as sibling `remote-ci-economics-workspace/`); generate the review viewer.
4. After user review, iterate; then offer description optimization (`run_loop.py`).
5. Pilot repository changes (e.g., goldrush push-e2e removal) only after explicit user
   approval, via `/orchestration` + independent Orca worktrees, separate commit/PR per repo.
   The audit itself must never trigger workflows or change settings.

## Fixture archetypes (grounded in real cases observed this session)

- active workflow with PR+push duplication and a heavy job (goldrush shape)
- branch-only workflow spending minutes with clean default branch (samhaengsi shape)
- cost-motivated deletion history + slim conditional CI (medicount shape)
- billing-block window: instant-dead jobs + annotations + flat usage during red runs
- quota near-exhaustion with $0 prevent_further_usage budget
- macOS multiplier dominating quota despite small raw minutes (ultari shape)
- org months with missing usage (pre-transfer) alongside existing runs
- no workflows and no runs at all (true negative; distinct from branch-only case)
- unreadable billing endpoints (errors recorded, findings marked unknown)
- plan unknown → no quota projection emitted

## Acceptance criteria (carried forward, still binding)

- The audit never triggers workflows or mutates repository/organization settings.
- Every external-state or cost claim has source and observation date; unknowns stay unknown.
- Findings distinguish confirmed / risk / opportunity / unknown.
- Recommendations preserve required verification coverage or explicitly state the trade-off.
- E2E/pgTAP placed by risk, runtime, frequency, and feedback latency — never removed categorically.
- Savings estimates are reproducible from stated inputs and never presented as observed billing.
- "No optimization justified" is a valid, complete result.
- The skill stays domain-neutral and independent of any pilot at runtime.

## Repository operation note

Working tree has the uncommitted changes listed above. Follow the repository rule: do not
commit or push `sleeptimegrt-skills` unless the user explicitly requests it.

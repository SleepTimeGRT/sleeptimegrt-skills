# Lifecycle Gate Policy Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `harness-conventions` skill to `lifecycle-gate-policy` in this repo (the canonical source), correcting every leftover `orca-review-gate`/"cross-model review" reference and every self-referential `harness-conventions` string, and resolve the `token-gate.sh` ownership bug by deleting the orphan copy in `token-efficient-gates` — migrating its test coverage in the same change — while keeping the repo's existing 38-test baseline green throughout.

**Architecture:** This is a rename-and-correct migration over existing files, not new functionality. Work proceeds file-by-file: one `git mv` for the directory, then one task per file (or tightly-coupled file pair) so no two tasks touch the same file. A final task runs a fixture-based end-to-end audit plus a repo-wide grep sweep to prove no stale reference survives.

**Tech Stack:** Bash, Python 3 (stdlib only — `scripts/audit.py` has no third-party dependencies), Markdown/YAML frontmatter.

**Source spec:** `docs/superpowers/specs/2026-07-22-lifecycle-gate-policy-design.md` (Approved).

## Global Constraints

- New skill directory and frontmatter `name` are `lifecycle-gate-policy` (lowercase kebab-case) — no compatibility shim, no re-export, no leftover directory or symlink at the old `harness-conventions` path.
- This skill's responsibility **stops at merge into the default branch**; deploy-time gating is explicitly out of scope (spec "범위" decision).
- `token-efficient-gates/SKILL.md` gets exactly one added sentence, landing inside an **existing** section — do not invent a new "Boundaries"-style section there (spec: "새 구조를 만들지 않고 기존 절에 문장만 덧붙인다").
- Every sibling-skill mention in the rewritten `lifecycle-gate-policy` Boundaries section must read as a citation of rationale, not a runtime dependency — the shipped templates (`.githooks/*`, `premerge.sh`, `token-gate.sh`, `agents-policy.md`) and `scripts/audit.py` must keep working with zero sibling skills installed.
- Per this repo's `AGENTS.md`: **do not push this repository, and do not apply this work to `main`, unless the user explicitly requests it.** This plan executes inside an isolated worktree on branch `worktree-lifecycle-gate-policy-rename` (created via `EnterWorktree`, never `main`). The user has explicitly authorized per-task commits scoped to this branch only, since subagent-driven-development's review packages are diffed between commits — that authorization does not extend to `git push` or to merging/rebasing onto `main`, both of which still require a separate, explicit go-ahead (handled at the end via `superpowers:finishing-a-development-branch`).
- Per this repo's `AGENTS.md`: do not run deploy/release/migration/seed/wipe commands merely to measure output. The fixture repo built in Task 9 is a disposable scratch directory outside this repo, built solely to exercise `audit.py` read-only; it is deleted at the end of that task.
- **Baseline test suite must stay green throughout.** `tests/test_token_efficient_gates.py` and `tests/test_orca_skills.py` currently pass 38/38 (`uv run --with pytest pytest tests/ -q`; `pytest` is not installed globally in this environment — use `uv run --with pytest pytest ...` rather than a bare `pytest` invocation). `tests/test_token_efficient_gates.py`'s `RunnerTests` class (11 tests) `source`s `skills/token-efficient-gates/assets/token-gate.sh` directly — this was discovered during pre-flight baseline verification, after the plan below was first drafted without inspecting `tests/`. Task 8 now migrates that coverage in the same atomic change as the deletion it depends on, specifically so the suite is never red between tasks.

## Out of Scope (explicitly settled by this plan, per spec's request)

The design spec (line 190) asks this plan to settle the timing of two follow-on steps. Both are **deferred, not scheduled**:

1. **Pilot-repo reapplication** (`medicount`, `toss-samhaengsi`, `toss-space-goldrush`) — the spec requires this to be requested explicitly, per repo, after this rename lands (spec migration step 2). No task in this plan touches those repos except read-only `audit.py` runs for verification (Task 9), which change nothing on disk there.
2. **3-agent skill-pool symlink deployment** (`~/.claude/skills`, `~/.codex/skills`, `~/.agents/skills`, `~/.gemini/config/skills`) — the spec confirms no symlink or copy of this skill exists in any pool yet, so there is nothing to migrate; deploying fresh is a separate, later request (spec migration step 3).

Rationale for deferring both here: this plan's blast radius is intentionally limited to the canonical skill directory inside `sleeptimegrt-skills`. Touching other repositories or other machines' skill pools in the same plan would mix an internal rename with external, harder-to-reverse changes, which the spec's own migration section already separates into distinct, separately-approved steps.

---

### Task 1: Rename the skill directory

**Files:**
- Modify (rename): `skills/harness-conventions/` → `skills/lifecycle-gate-policy/` (all 12 files move as-is; content changes happen in later tasks)

**Interfaces:**
- Produces: the `skills/lifecycle-gate-policy/` path that every subsequent task edits into.

- [ ] **Step 1: Confirm starting state**

```bash
cd "$(git rev-parse --show-toplevel)"
test -d skills/harness-conventions && echo "source exists"
test -e skills/lifecycle-gate-policy && echo "UNEXPECTED: target already exists" || echo "target path is free"
```

Expected: `source exists` and `target path is free`.

**Run every command in this task from the repo root of the worktree you were told to work from — never `/Users/minchul/Projects/sleeptimegrt-skills` (that is the main checkout on `main`; this plan runs inside an isolated worktree on its own branch). `$(git rev-parse --show-toplevel)` resolves correctly from either.**

- [ ] **Step 2: Rename with git so history follows the files**

```bash
cd "$(git rev-parse --show-toplevel)"
git mv skills/harness-conventions skills/lifecycle-gate-policy
```

- [ ] **Step 3: Verify the rename**

```bash
git status --short
find skills/lifecycle-gate-policy -type f | sort
```

Expected: `git status --short` shows 12 lines of the form `R  skills/harness-conventions/<f> -> skills/lifecycle-gate-policy/<f>`. The `find` output lists the same 12 files as before (SKILL.md, assets/agents-policy.md, assets/githooks/{post-checkout,pre-commit,pre-push,worktree-links.conf}, assets/scripts/{premerge.conf.sh,premerge.sh,token-gate.sh}, references/policy-rationale.md, scripts/audit.py), now under `skills/lifecycle-gate-policy/`.

Do not commit. Leave the rename staged.

---

### Task 2: Rewrite `SKILL.md` identity and Boundaries

**Files:**
- Modify: `skills/lifecycle-gate-policy/SKILL.md`

**Interfaces:**
- Consumes: the path produced by Task 1.
- Produces: the frontmatter `name`/`description` that skill discovery matches on, and the Boundaries text Task 8 cross-checks against.

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "^name:\|^description:\|^# \|cross-model\|orca-review-gate" skills/lifecycle-gate-policy/SKILL.md
```

Expected: hits at line 2 (`name: harness-conventions`), line 3 (`description: '...'`), line 6 (`# Harness Conventions`), line 21 (cross-model), line 24 (orca-review-gate), line 87 (orca-review-gate).

- [ ] **Step 2: Rename the skill (frontmatter `name`)**

Old:
```
name: harness-conventions
```
New:
```
name: lifecycle-gate-policy
```

- [ ] **Step 3: Replace the frontmatter `description`**

Old (the entire line 3, verbatim):
```
description: 'Canonical cross-repository development-harness policy, drift audit, and apply templates: three-layer local gates (pre-commit secrets+autofix, static-only pre-push, full premerge verify+e2e), agent self-merge rules with mechanical gate-integrity protection, .githooks templates, and a package-script naming contract. Use whenever the user asks to review, compare, unify, audit, standardize, or set up a repository''s development harness, git hooks, verify chains, merge or self-merge policy, premerge gates, or worktree conventions — and before hand-editing any .githooks/, token-gate, or premerge file in a repository that follows this convention, since those files are canonical copies managed here. Excludes remote CI cost judgment (remote-ci-economics) and agent-facing output compaction design (token-efficient-gates).'
```
New (single line, note the `''` escaping for the apostrophe in "repository's" — matches this file's existing YAML single-quote convention):
```
description: 'Canonical local development-lifecycle gate policy for solo, agent-driven repositories with no remote-CI enforcement: pre-commit secret scan + autofix, static-only pre-push, full premerge verify+e2e, and agent self-merge with mechanical gate-integrity protection — the local substitute for what remote CI and branch protection would otherwise enforce. Ships canonical .githooks/ and premerge/token-gate templates with a hash-based drift audit so N repos share one answer instead of drifting independently. Use whenever the user asks to review, compare, unify, audit, standardize, or set up a repository''s development gates, git hooks, verify chains, merge or self-merge policy, premerge gates, or worktree conventions — and before hand-editing any .githooks/, token-gate, or premerge file in a repository that follows this convention, since those files are canonical copies managed here. Stops at merge into the default branch; does not cover deploy-time gating. Excludes remote CI cost judgment (remote-ci-economics) and generic agent-facing output compaction (token-efficient-gates) — cross-references their conclusions but ships nothing that requires either to be present.'
```

- [ ] **Step 4: Rename the title**

Old:
```
# Harness Conventions
```
New:
```
# Lifecycle Gate Policy
```

- [ ] **Step 5: Drop "cross-model" from the summary table row (line 21)**

Old:
```
| `scripts/premerge.sh` | before squash merge | sync check → gate-integrity check → cross-model review requirement → full `pnpm verify` → e2e |
```
New:
```
| `scripts/premerge.sh` | before squash merge | sync check → gate-integrity check → review requirement → full `pnpm verify` → e2e |
```

- [ ] **Step 6: Drop the `orca-review-gate` name from the self-merge sentence (line 24)**

Old:
```
Self-merge: the authoring agent may merge its own PR when `premerge.sh` passes
(including `--review-done` after a clean `orca-review-gate` run for code changes).
```
New:
```
Self-merge: the authoring agent may merge its own PR when `premerge.sh` passes
(including `--review-done` after a clean review pass for code changes).
```

- [ ] **Step 7: Rewrite the Boundaries section**

Old (the full section):
```
## Boundaries

- **token-efficient-gates** owns agent-facing output economics; its `capture.py` is
  for ad-hoc agent runs, while the `token-gate.sh` template here is the persistent
  in-repo adapter. Keep their design constraints (PASS one-liner, bounded indexes).
- **remote-ci-economics** owns whether remote CI should exist at all; this skill
  only reports workflow presence.
- **orca-review-gate** executes the cross-model review that `premerge.sh` requires
  for code changes; this skill defines *when* it is required, not how it runs.
- **superpowers** skills (finishing-a-development-branch, using-git-worktrees) stay
  useful as generic procedure; the AGENTS.md policy template supplies the declared
  preferences (worktree location, merge choice) those skills ask about.
```
New:
```
## Boundaries

Every sibling-skill mention below is a citation of rationale, not a runtime
dependency: the deployed templates (`.githooks/*`, `premerge.sh`, `token-gate.sh`,
`agents-policy.md`) and `scripts/audit.py` work correctly even if neither sibling
skill is installed.

- **token-efficient-gates** owns agent-facing output economics; its `capture.py` is
  for ad-hoc agent runs, while the `token-gate.sh` template here is the persistent
  in-repo adapter. Keep their design constraints (PASS one-liner, bounded indexes).
- **remote-ci-economics** owns whether remote CI should exist at all; this skill
  only reports workflow presence.
- This skill defines *when* a review pass is required (`--review-done`) for code
  changes; it is agnostic to what fills that signal.
- **superpowers** skills (finishing-a-development-branch, using-git-worktrees) stay
  useful as generic procedure; the AGENTS.md policy template supplies the declared
  preferences (worktree location, merge choice) those skills ask about.
```

- [ ] **Step 8: Verify**

```bash
grep -n "^name:\|^description:\|^# " skills/lifecycle-gate-policy/SKILL.md
grep -c "harness-conventions\|orca-review-gate\|cross-model" skills/lifecycle-gate-policy/SKILL.md
```

Expected: `name: lifecycle-gate-policy`, the new description line, `# Lifecycle Gate Policy`; the `grep -c` count is `0`.

---

### Task 3: Fix `assets/agents-policy.md`

**Files:**
- Modify: `skills/lifecycle-gate-policy/assets/agents-policy.md`

**Interfaces:**
- Consumes: path from Task 1.
- Produces: the marker string Task 6's `POLICY_MARKER` and Task 9's fixture check must match byte-for-byte.

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "harness-conventions\|cross-model\|orca-review-gate" skills/lifecycle-gate-policy/assets/agents-policy.md
```

Expected: hits at lines 1, 10, 22.

- [ ] **Step 2: Rename the drift-audit marker (line 1)**

Old:
```
<!-- harness-conventions: policy v1 — keep this marker line; the drift audit checks for it. -->
```
New:
```
<!-- lifecycle-gate-policy: policy v1 — keep this marker line; the drift audit checks for it. -->
```

- [ ] **Step 3: Drop "cross-model" from the summary table row (line 10)**

Old:
```
| `scripts/premerge.sh` | right before squash merge | full `pnpm verify` + e2e (if configured) + cross-model review for code changes | final gate |
```
New:
```
| `scripts/premerge.sh` | right before squash merge | full `pnpm verify` + e2e (if configured) + review for code changes | final gate |
```

- [ ] **Step 4: Fix the self-merge bullet (lines 20-22) — replace the whole bullet, not just the `orca-review-gate` clause**

The line already contains the words "a clean" immediately before the text being replaced. Substituting only `` cross-model review (`orca-review-gate` skill) `` → `a clean review pass` would leave a duplicated "a clean a clean review pass". Replace all three lines as one block:

Old:
```
- **Self-merge**: the agent that authored a PR may merge it itself when
  `scripts/premerge.sh` exits PASS. For code changes this includes a clean
  cross-model review (`orca-review-gate` skill), then `premerge.sh --review-done`.
```
New:
```
- **Self-merge**: the agent that authored a PR may merge it itself when
  `scripts/premerge.sh` exits PASS. For code changes this includes a clean
  review pass, then `premerge.sh --review-done`.
```

- [ ] **Step 5: Verify**

```bash
grep -n "harness-conventions\|cross-model\|orca-review-gate" skills/lifecycle-gate-policy/assets/agents-policy.md
grep -n "a clean a clean" skills/lifecycle-gate-policy/assets/agents-policy.md
```

Expected: both commands print nothing.

---

### Task 4: Fix `assets/scripts/premerge.sh` and `assets/scripts/premerge.conf.sh`

**Files:**
- Modify: `skills/lifecycle-gate-policy/assets/scripts/premerge.sh`
- Modify: `skills/lifecycle-gate-policy/assets/scripts/premerge.conf.sh`

**Interfaces:**
- Consumes: path from Task 1.
- Produces: the canonical `premerge.sh`/`premerge.conf.sh` content that Task 9's fixture and pilot-repo drift check compare against.

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "harness-conventions\|cross-model" skills/lifecycle-gate-policy/assets/scripts/premerge.sh skills/lifecycle-gate-policy/assets/scripts/premerge.conf.sh
```

Expected: `premerge.sh` hits at lines 2, 13-14, 92, 97; `premerge.conf.sh` hits at lines 1, 10.

- [ ] **Step 2: `premerge.sh` line 2 — banner rename**

Old:
```
# harness-conventions: canonical scripts/premerge.sh v1 — do not hand-edit in the
```
New:
```
# lifecycle-gate-policy: canonical scripts/premerge.sh v1 — do not hand-edit in the
```

- [ ] **Step 3: `premerge.sh` lines 13-14 — exit-code comment**

Old:
```
#   4  REVIEW — code changes present and --review-done not given; run the
#      cross-model review gate first, then re-run with --review-done
```
New:
```
#   4  REVIEW — code changes present and --review-done not given; run your
#      review process first, then re-run with --review-done
```

- [ ] **Step 4: `premerge.sh` line 92 — section header**

Old:
```
# ---- 3. cross-model review requirement ----------------------------------------
```
New:
```
# ---- 3. review requirement ----------------------------------------------------
```

- [ ] **Step 5: `premerge.sh` line 97 — output message**

Old:
```
  printf '[premerge] run the cross-model review gate (orca-review-gate), resolve blocking findings,\n'
```
New:
```
  printf '[premerge] resolve blocking findings from your review process,\n'
```

- [ ] **Step 6: `premerge.conf.sh` line 1 — banner rename**

Old:
```
# harness-conventions: repo config (edit freely) — sourced by scripts/premerge.sh.
```
New:
```
# lifecycle-gate-policy: repo config (edit freely) — sourced by scripts/premerge.sh.
```

- [ ] **Step 7: `premerge.conf.sh` line 10 — comment**

Old:
```
# Files matching this regex do not require cross-model review (docs-only PRs).
```
New:
```
# Files matching this regex do not require review (docs-only PRs).
```

- [ ] **Step 8: Verify syntax and content**

```bash
bash -n skills/lifecycle-gate-policy/assets/scripts/premerge.sh
bash -n skills/lifecycle-gate-policy/assets/scripts/premerge.conf.sh
grep -c "harness-conventions\|cross-model\|orca-review-gate" skills/lifecycle-gate-policy/assets/scripts/premerge.sh skills/lifecycle-gate-policy/assets/scripts/premerge.conf.sh
```

Expected: both `bash -n` calls print nothing and exit 0 (valid syntax); both grep counts are `0`.

---

### Task 5: Rename the banner in the remaining templates (`token-gate.sh` + 3 githooks + `worktree-links.conf`)

These five files need only their self-referential `harness-conventions:` banner line renamed — no `orca-review-gate`/`cross-model` content exists in any of them (confirmed by the repo-wide grep during planning).

**Files:**
- Modify: `skills/lifecycle-gate-policy/assets/scripts/token-gate.sh`
- Modify: `skills/lifecycle-gate-policy/assets/githooks/pre-commit`
- Modify: `skills/lifecycle-gate-policy/assets/githooks/pre-push`
- Modify: `skills/lifecycle-gate-policy/assets/githooks/post-checkout`
- Modify: `skills/lifecycle-gate-policy/assets/githooks/worktree-links.conf`

**Interfaces:**
- Consumes: path from Task 1.
- Produces: canonical file content Task 9's fixture/pilot-drift check compares against.

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "harness-conventions" \
  skills/lifecycle-gate-policy/assets/scripts/token-gate.sh \
  skills/lifecycle-gate-policy/assets/githooks/pre-commit \
  skills/lifecycle-gate-policy/assets/githooks/pre-push \
  skills/lifecycle-gate-policy/assets/githooks/post-checkout \
  skills/lifecycle-gate-policy/assets/githooks/worktree-links.conf
```

Expected: exactly one hit per file, each on line 2 (line 1 for `worktree-links.conf`).

- [ ] **Step 2: `token-gate.sh` line 2**

Old:
```
# harness-conventions: canonical scripts/token-gate.sh v1 — do not hand-edit in the
```
New:
```
# lifecycle-gate-policy: canonical scripts/token-gate.sh v1 — do not hand-edit in the
```

- [ ] **Step 3: `pre-commit` line 2**

Old:
```
# harness-conventions: canonical .githooks/pre-commit v1 — do not hand-edit in the
```
New:
```
# lifecycle-gate-policy: canonical .githooks/pre-commit v1 — do not hand-edit in the
```

- [ ] **Step 4: `pre-push` line 2**

Old:
```
# harness-conventions: canonical .githooks/pre-push v1 — do not hand-edit in the
```
New:
```
# lifecycle-gate-policy: canonical .githooks/pre-push v1 — do not hand-edit in the
```

- [ ] **Step 5: `post-checkout` line 2**

Old:
```
# harness-conventions: canonical .githooks/post-checkout v1 — do not hand-edit in the
```
New:
```
# lifecycle-gate-policy: canonical .githooks/post-checkout v1 — do not hand-edit in the
```

- [ ] **Step 6: `worktree-links.conf` line 1**

Old:
```
# harness-conventions: repo config (edit freely) — worktree symlink list.
```
New:
```
# lifecycle-gate-policy: repo config (edit freely) — worktree symlink list.
```

- [ ] **Step 7: Verify**

```bash
grep -rn "harness-conventions" \
  skills/lifecycle-gate-policy/assets/scripts/token-gate.sh \
  skills/lifecycle-gate-policy/assets/githooks/
bash -n skills/lifecycle-gate-policy/assets/scripts/token-gate.sh
bash -n skills/lifecycle-gate-policy/assets/githooks/pre-commit
bash -n skills/lifecycle-gate-policy/assets/githooks/pre-push
bash -n skills/lifecycle-gate-policy/assets/githooks/post-checkout
```

Expected: the `grep -rn` call prints nothing; all four `bash -n` calls exit 0 with no output. (`token-gate.sh` is meant to be sourced, not executed, but `bash -n` still validates its syntax without running it.)

---

### Task 6: Fix `scripts/audit.py`

**Files:**
- Modify: `skills/lifecycle-gate-policy/scripts/audit.py`

**Interfaces:**
- Consumes: path from Task 1.
- Produces: `POLICY_MARKER` value that Task 9 checks for exact equality against `assets/agents-policy.md` line 1 (Task 3's output).

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "harness-conventions" skills/lifecycle-gate-policy/scripts/audit.py
```

Expected: hits at lines 2 and 41.

- [ ] **Step 2: Docstring (line 2)**

Old:
```
"""Read-only drift audit for the harness-conventions policy.
```
New:
```
"""Read-only drift audit for the lifecycle-gate-policy skill.
```

- [ ] **Step 3: `POLICY_MARKER` constant (line 41)**

Old:
```
POLICY_MARKER = "harness-conventions: policy v1"
```
New:
```
POLICY_MARKER = "lifecycle-gate-policy: policy v1"
```

- [ ] **Step 4: Verify**

```bash
python3 -c "import ast; ast.parse(open('skills/lifecycle-gate-policy/scripts/audit.py').read())" && echo "syntax OK"
grep -n "harness-conventions" skills/lifecycle-gate-policy/scripts/audit.py
grep -n 'POLICY_MARKER = ' skills/lifecycle-gate-policy/scripts/audit.py
```

Expected: `syntax OK`; the `harness-conventions` grep prints nothing; the `POLICY_MARKER` grep shows `POLICY_MARKER = "lifecycle-gate-policy: policy v1"`.

---

### Task 7: Fix `references/policy-rationale.md`

**Files:**
- Modify: `skills/lifecycle-gate-policy/references/policy-rationale.md`

**Interfaces:**
- Consumes: path from Task 1.

- [ ] **Step 1: Capture the before-state**

```bash
grep -n "harness-conventions\|cross-model" skills/lifecycle-gate-policy/references/policy-rationale.md
```

Expected: hits at lines 3, 52, 57.

- [ ] **Step 2: Line 3 — drop the self-name (avoids an awkward "policy policy")**

Old:
```
Why each rule in the harness-conventions policy exists. Claims from external
```
New:
```
Why each rule in this policy exists. Claims from external
```

- [ ] **Step 3: Line 52 — replace the cross-model rationale with this session's confirmed basis**

Old:
```
- Observed failure modes that motivate the mechanical PROTECTED check: agents
  removing tests or skipping lint steps to pass CI (GitHub blog, 2026-05-07
  [fetched]); reward hacking of the measuring function (o3 example [snippet]);
  same-model review sharing correlated blind spots (Vaughan, 2026-05-24
  [fetched]) — mitigated here by the review being cross-model.
```
New:
```
- Observed failure modes that motivate the mechanical PROTECTED check: agents
  removing tests or skipping lint steps to pass CI (GitHub blog, 2026-05-07
  [fetched]); reward hacking of the measuring function (o3 example [snippet]);
  same-model review sharing correlated blind spots (Vaughan, 2026-05-24
  [fetched]) — mitigated here by fresh-context and a skeptical review prompt,
  not by cross-provider separation (this repo's `/advisor` shows same-provider
  review is effective too).
```

- [ ] **Step 4: Line 57 — drop "Cross-model"**

Old:
```
verify/e2e/review — never to revoke self-merge. Cross-model review is required
for code changes only; docs-only PRs pass on verify(+e2e) to keep trivial-PR
throughput and token cost sane.
```
New:
```
verify/e2e/review — never to revoke self-merge. A review pass is required
for code changes only; docs-only PRs pass on verify(+e2e) to keep trivial-PR
throughput and token cost sane.
```

- [ ] **Step 5: Verify**

```bash
grep -n "harness-conventions\|cross-model" skills/lifecycle-gate-policy/references/policy-rationale.md
```

Expected: prints nothing.

---

### Task 8: Resolve `token-gate.sh` ownership — delete the `token-efficient-gates` orphan, migrate its test coverage, document the pointer

This task deletes the orphan file and moves the tests that exercise it in one atomic change — the deletion is not safe to review or land on its own, since `tests/test_token_efficient_gates.py::RunnerTests` sources the exact path being deleted.

**Files:**
- Delete: `skills/token-efficient-gates/assets/token-gate.sh`
- Modify: `skills/token-efficient-gates/SKILL.md`
- Modify: `tests/test_token_efficient_gates.py` (remove `RunnerTests`, its now-dead `RUNNER` constant, and its now-unused `shlex` import)
- Create: `tests/test_lifecycle_gate_policy.py` (receives `RunnerTests`, repointed at the new canonical path)

**Interfaces:**
- Consumes: the fact (confirmed during planning) that no script in `token-efficient-gates` (`capture.py`, `measure.py`, `scripts/audit.py`) references `assets/token-gate.sh` by path — only `token-gate.sh` itself defines the `token_gate_*` shell functions, which is a separate, unrelated naming convention from `capture.py`'s own `token-gates-<uid>` log directory.
- Consumes: `skills/lifecycle-gate-policy/assets/scripts/token-gate.sh` must already exist with its Task 1 (rename) and Task 5 (banner fix) content applied — `RunnerTests` sources this exact path.
- Produces: nothing consumed by other tasks. This task is independent of Tasks 2-7.

- [ ] **Step 1: Confirm the file is a true orphan (already checked during planning; re-confirm before deleting)**

```bash
grep -rn "token-gate\.sh" skills/token-efficient-gates/ 2>/dev/null
```

Expected: no output — nothing in `token-efficient-gates` references the file by name (only the file's own internal `token_gate_*` function names show up, which is expected and unrelated).

- [ ] **Step 2: Capture the RunnerTests before-state**

```bash
grep -n "^class \|^RUNNER\|^import shlex" tests/test_token_efficient_gates.py
uv run --with pytest pytest tests/test_token_efficient_gates.py -q
```

Expected: `class GitFixture`, `class AuditTests`, `class RunnerTests`, `class MeasureTests`, `class CaptureTests`; `RUNNER = ROOT / "skills" / "token-efficient-gates" / "assets" / "token-gate.sh"`; `import shlex`. All tests in the file pass (part of the 38-test baseline).

- [ ] **Step 3: Create `tests/test_lifecycle_gate_policy.py` with `GitFixture` + `RunnerTests`, repointed**

This duplicates `run()`, `retained_log()`, and `GitFixture` rather than sharing them via a new helper module — the two test files are not meant to import each other, and introducing a shared `conftest.py` is a bigger abstraction than this migration calls for.

```python
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
RUNNER = ROOT / "skills" / "lifecycle-gate-policy" / "assets" / "scripts" / "token-gate.sh"


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


def retained_log(stdout: str) -> Path:
    line = next(line for line in stdout.splitlines() if "log:" in line)
    return Path(line.split(" — log: ", 1)[1])


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="lifecycle gate policy ")
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


class RunnerTests(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.runtime_tmp = (Path(self.tempdir.name) / "runtime tmp").resolve()
        self.runtime_tmp.mkdir(mode=0o700)

    def runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["TMPDIR"] = str(self.runtime_tmp)
        return env

    def run_gate(self, body: str) -> subprocess.CompletedProcess[str]:
        script = self.write(
            "run-gate.sh",
            f"""
            #!/usr/bin/env bash
            set -u
            source {json.dumps(str(RUNNER))}
            token_gate_begin verify
            {body}
            token_gate_finish
            """,
            True,
        )
        return run("bash", str(script), cwd=self.repo, check=False, env=self.runtime_env())

    def run_capture(self, command: str, *options: str) -> subprocess.CompletedProcess[str]:
        script = self.write(
            "run-capture.sh",
            f"""
            #!/usr/bin/env bash
            set -u
            source {json.dumps(str(RUNNER))}
            token_gate_capture {' '.join(options)} verify -- bash -c {shlex.quote(command)}
            """,
            True,
        )
        return run("bash", str(script), cwd=self.repo, check=False, env=self.runtime_env())

    def test_whole_command_capture_hides_success_log_path(self) -> None:
        result = self.run_capture("printf 'noisy-success\\n%.0s' {1..100}")

        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r"^\[verify\] PASS \([0-9]+s\)\n$")
        self.assertNotIn("log:", result.stdout)
        self.assertNotIn("noisy-success", result.stdout)
        self.assertEqual(list(self.runtime_tmp.rglob("latest.log")), [])
        self.assertEqual(list((self.repo / ".git" / "token-gates").rglob("latest.log")), [])

    def test_whole_command_failure_returns_bounded_line_index(self) -> None:
        result = self.run_capture(
            "printf 'progress-%s\\n' {1..30}; "
            "echo 'src/check.ts:14:3 error TS2322: wrong type'; "
            "printf 'after-%s\\n' {1..20}; exit 19"
        )

        self.assertEqual(result.returncode, 19)
        lines = result.stdout.splitlines()
        self.assertRegex(lines[0], r"^\[verify\] FAIL \(exit 19, [0-9]+s\) — log: .+/latest\.log$")
        self.assertEqual(lines[1], "[verify] INDEX L31: src/check.ts:14:3 error TS2322: wrong type")
        self.assertEqual(len(lines), 2)
        self.assertTrue(retained_log(result.stdout).is_relative_to(self.runtime_tmp))

    def test_whole_command_warning_uses_explicit_detector(self) -> None:
        result = self.run_capture("echo 'NOTICE quota nearing limit'", "--warn-regex", "'^NOTICE '")

        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout.splitlines()[0], r"^\[verify\] WARN \([0-9]+s\) — log: .+/latest\.log$")
        self.assertEqual(result.stdout.splitlines()[1], "[verify] INDEX L1: NOTICE quota nearing limit")

    def test_whole_command_failure_without_marker_points_to_tail(self) -> None:
        result = self.run_capture("printf 'opaque-%s\\n' {1..37}; exit 2")

        self.assertEqual(result.returncode, 2)
        self.assertIn("[verify] INDEX no high-confidence marker; inspect L18-L37", result.stdout)
        self.assertNotIn("opaque-37", result.stdout)

    def test_whole_command_capture_re_raises_signal(self) -> None:
        result = self.run_capture("kill -TERM $$")

        self.assertEqual(result.returncode, -15)
        self.assertRegex(
            result.stdout.splitlines()[0],
            r"^\[verify\] FAIL \(signal (?:TERM|15), [0-9]+s\) — log: .+/latest\.log$",
        )

    def test_runner_compacts_pass_warn_and_fail_while_preserving_diagnostics(self) -> None:
        result = self.run_gate(
            """
            token_gate_stage pass -- bash -c 'echo many; echo lines'
            token_gate_stage --warn-regex 'deprecated' vocab -- bash -c 'echo deprecated >&2'
            token_gate_stage broken -- bash -c 'echo failure detail >&2; exit 23'
            exit $?
            """
        )

        self.assertEqual(result.returncode, 23)
        self.assertNotIn("many", result.stdout)
        self.assertNotIn("failure detail", result.stdout)
        self.assertRegex(result.stdout, r"\[verify\] PASS pass \([0-9.]+s\)")
        self.assertRegex(result.stdout, r"\[verify\] WARN vocab \([0-9.]+s\) — log: .+")
        self.assertRegex(result.stdout, r"\[verify\] FAIL broken \(exit 23, [0-9.]+s\) — log: .+")

        log_path = retained_log(result.stdout)
        self.assertTrue(log_path.is_file())
        self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("many", log)
        self.assertIn("deprecated", log)
        self.assertIn("failure detail", log)
        self.assertEqual(run("git", "status", "--porcelain=v1", cwd=self.repo).stdout.count("token-gates"), 0)

    def test_runner_deletes_log_after_all_stages_pass(self) -> None:
        result = self.run_gate("token_gate_stage first -- bash -c 'echo success-marker'")

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("log:", result.stdout)
        self.assertEqual(list(self.runtime_tmp.rglob("latest.log")), [])

    def test_runner_preserves_signal_termination(self) -> None:
        result = self.run_gate("token_gate_stage signaled -- bash -c 'kill -TERM $$'")

        self.assertEqual(result.returncode, -15)
        self.assertRegex(result.stdout, r"\[verify\] FAIL signaled \(signal (?:TERM|15), [0-9.]+s\) — log: .+")

    def test_runner_reports_skip_as_a_distinct_outcome(self) -> None:
        result = self.run_gate("token_gate_skip integration 'database is unavailable'")

        self.assertEqual(result.returncode, 0)
        self.assertIn("[verify] SKIP integration — database is unavailable", result.stdout)
        self.assertIn("[verify] WARN 1 stages", result.stdout)

    def test_runner_accumulates_failure_when_the_caller_continues(self) -> None:
        result = self.run_gate(
            """
            token_gate_stage broken -- bash -c 'echo broken-detail; exit 7' || true
            token_gate_stage later -- bash -c 'echo later-detail'
            """
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("[verify] FAIL broken (exit 7", result.stdout)
        self.assertIn("[verify] PASS later", result.stdout)
        self.assertIn("[verify] FAIL 2 stages", result.stdout)

    def test_runner_isolates_logs_between_linked_worktrees(self) -> None:
        self.write("tracked.txt", "fixture\n")
        run("git", "config", "user.email", "fixture@example.test", cwd=self.repo)
        run("git", "config", "user.name", "Fixture", cwd=self.repo)
        run("git", "commit", "-qm", "fixture", cwd=self.repo)
        linked = Path(self.tempdir.name) / "linked worktree"
        run("git", "worktree", "add", "-q", "-b", "linked", str(linked), cwd=self.repo)

        main_result = self.run_gate(
            "token_gate_stage --warn-regex warning main -- bash -c 'echo main-warning'"
        )
        linked_script = linked / "linked-gate.sh"
        linked_script.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                source {json.dumps(str(RUNNER))}
                token_gate_begin verify
                token_gate_stage --warn-regex warning linked -- bash -c 'echo linked-warning'
                token_gate_finish
                """
            ).lstrip(),
            encoding="utf-8",
        )
        linked_result = run("bash", str(linked_script), cwd=linked, check=False, env=self.runtime_env())

        main_log = retained_log(main_result.stdout)
        linked_log = retained_log(linked_result.stdout)
        self.assertNotEqual(main_log, linked_log)
        self.assertIn("main-warning", main_log.read_text(encoding="utf-8"))
        self.assertIn("linked-warning", linked_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Remove `RunnerTests` and its now-dead imports/constant from `tests/test_token_efficient_gates.py`**

Delete the entire `class RunnerTests(GitFixture):` block — from its `class RunnerTests(GitFixture):` line through the line immediately before `class MeasureTests(GitFixture):` (i.e. everything shown in Step 3 above under "class RunnerTests", as it appeared in the original file, including its trailing blank lines down to — but not including — `class MeasureTests(GitFixture):`).

Then remove the now-unused import and constant:

Old:
```
from pathlib import Path
import shlex
import stat
```
New:
```
from pathlib import Path
import stat
```

Old:
```
MEASURE = ROOT / "skills" / "token-efficient-gates" / "scripts" / "measure.py"
RUNNER = ROOT / "skills" / "token-efficient-gates" / "assets" / "token-gate.sh"
```
New:
```
MEASURE = ROOT / "skills" / "token-efficient-gates" / "scripts" / "measure.py"
```

- [ ] **Step 5: Delete the orphan copy**

```bash
git rm skills/token-efficient-gates/assets/token-gate.sh
```

- [ ] **Step 6: Add the ownership pointer to `SKILL.md`**

The spec asks for this sentence to land "near the 'Stop at the remote boundary' section." This plan places it at the end of the immediately preceding section ("Modify a target only by explicit request"), which already discusses persistent adapters and sits directly above "Stop at the remote boundary" — stated here explicitly as a judgment call, not spec drift.

Old:
```
When applying a persistent adapter, preserve stage order, conditions, exit codes, signals, and fail-fast or aggregate-failure behavior. Never make the target repository depend on this skills repository at runtime.

## Stop at the remote boundary
```
New:
```
When applying a persistent adapter, preserve stage order, conditions, exit codes, signals, and fail-fast or aggregate-failure behavior. Never make the target repository depend on this skills repository at runtime.

If a persistent in-repo adapter is already needed, reference the `token-gate.sh` that `lifecycle-gate-policy` ships instead of authoring a second copy here.

## Stop at the remote boundary
```

- [ ] **Step 7: Verify**

```bash
test -e skills/token-efficient-gates/assets/token-gate.sh && echo "UNEXPECTED: file still present" || echo "orphan removed"
find skills/token-efficient-gates/assets -type f
grep -n "lifecycle-gate-policy" skills/token-efficient-gates/SKILL.md
grep -c "class RunnerTests\|^import shlex\|^RUNNER = " tests/test_token_efficient_gates.py
uv run --with pytest pytest tests/test_token_efficient_gates.py tests/test_lifecycle_gate_policy.py -q
```

Expected: `orphan removed`; the `find` call prints nothing (the `assets/` directory is now empty); the `grep` call on `SKILL.md` shows the one new sentence; the `grep -c` on `test_token_efficient_gates.py` prints `0`; both test files pass, and the combined count equals the original file's full count (the 11 `RunnerTests` methods now live in `test_lifecycle_gate_policy.py`, nothing lost, nothing duplicated across both files).

---

### Task 9: Final verification — fixture audit, marker-consistency check, repo-wide sweep

This task has no source edits of its own; it proves Tasks 1-8 together produced a self-consistent, working skill.

**Files:**
- Read-only: everything under `skills/lifecycle-gate-policy/`, `skills/token-efficient-gates/`, and `tests/`
- Scratch (created and destroyed within this task): a fixture git repository under the scratchpad directory

**Interfaces:**
- Consumes: the final content of every file touched in Tasks 1-8.

- [ ] **Step 1: Run the full test suite**

```bash
cd "$(git rev-parse --show-toplevel)"
uv run --with pytest pytest tests/ -q
```

Expected: `38 passed` (same total as the pre-flight baseline — Task 8 moved 11 tests to a new file, it did not add or remove test cases).

- [ ] **Step 2: Repo-wide grep sweep for stale references**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rln "harness-conventions" . --include="*.md" --include="*.py" --include="*.sh" --include="*.conf" 2>/dev/null | grep -v "docs/superpowers/specs/"
grep -rn "orca-review-gate\|cross-model" skills/lifecycle-gate-policy/ 2>/dev/null
```

Expected: both commands print nothing. (The design spec under `docs/superpowers/specs/` is a dated historical record and is intentionally excluded — it describes what changed, so it correctly keeps saying "harness-conventions" and "cross-model" when quoting the old text.)

- [ ] **Step 3: Direct marker-consistency check**

This is the one invariant a pilot-repo audit run cannot distinguish from a typo: `scripts/audit.py`'s `POLICY_MARKER` constant must be byte-identical to the marker line shipped in `assets/agents-policy.md`, since `audit.py` checks a target repo's `AGENTS.md` by substring match against `POLICY_MARKER`.

```bash
grep -o "lifecycle-gate-policy: policy v1" skills/lifecycle-gate-policy/scripts/audit.py
grep -o "lifecycle-gate-policy: policy v1" skills/lifecycle-gate-policy/assets/agents-policy.md
```

Expected: both commands print the identical string `lifecycle-gate-policy: policy v1`. If either is empty, stop and re-check Task 3 Step 2 or Task 6 Step 3 before continuing.

- [ ] **Step 4: Build a disposable fixture repo and run `audit.py` end-to-end**

```bash
cd "$(git rev-parse --show-toplevel)"
SKILL_DIR="$(pwd)/skills/lifecycle-gate-policy"
FIXTURE=/private/tmp/claude-501/-Users-minchul-Projects-sleeptimegrt-skills/d7851cfa-3123-4930-8104-4e857942690c/scratchpad/lgp-fixture

rm -rf "$FIXTURE"
mkdir -p "$FIXTURE/.githooks" "$FIXTURE/scripts"
cd "$FIXTURE"
git init -q

cp "$SKILL_DIR/assets/githooks/pre-commit" .githooks/
cp "$SKILL_DIR/assets/githooks/pre-push" .githooks/
cp "$SKILL_DIR/assets/githooks/post-checkout" .githooks/
cp "$SKILL_DIR/assets/githooks/worktree-links.conf" .githooks/
cp "$SKILL_DIR/assets/scripts/premerge.sh" scripts/
cp "$SKILL_DIR/assets/scripts/token-gate.sh" scripts/
cp "$SKILL_DIR/assets/scripts/premerge.conf.sh" scripts/
cp "$SKILL_DIR/assets/agents-policy.md" AGENTS.md
chmod +x .githooks/pre-commit .githooks/pre-push .githooks/post-checkout scripts/premerge.sh
git config core.hooksPath .githooks

cat > package.json <<'EOF'
{
  "scripts": {
    "prepare": "git config core.hooksPath .githooks",
    "verify": "true",
    "verify:static": "true",
    "premerge": "bash scripts/premerge.sh"
  }
}
EOF

python3 "$SKILL_DIR/scripts/audit.py" --repo "$FIXTURE"
```

Expected output: every check line reads `PASS` (including `AGENTS.md policy` → `policy marker present`) except `.github/workflows` which reads `[   INFO] .github/workflows  no remote CI workflows` (informational, not a failure). The final line reads `lgp-fixture: COMPLIANT`, and the command's exit code is `0`.

- [ ] **Step 5: Clean up the fixture**

```bash
rm -rf "$FIXTURE"
```

- [ ] **Step 6: Read-only sanity check against a real pilot repo (expected to show new drift, not a crash)**

This does not modify the pilot repo. Its only purpose is to confirm `audit.py` still runs correctly from its new path and that the drift it reports matches exactly what Tasks 1-8 are expected to introduce — nothing more, nothing less.

```bash
cd "$(git rev-parse --show-toplevel)"
python3 skills/lifecycle-gate-policy/scripts/audit.py --repo /Users/minchul/Projects/medicount
```

Expected: `DRIFT` on exactly `.githooks/pre-commit`, `.githooks/pre-push`, `.githooks/post-checkout`, `scripts/premerge.sh`, and `scripts/token-gate.sh` (their canonical banner comment changed), `WARN` on `AGENTS.md policy` (the marker string changed and medicount has not been reapplied yet — expected and accepted per this plan's Out of Scope section), and the pre-existing `FAIL` on `.husky` (unrelated legacy leftover, not introduced by this plan). No other check should change status relative to this plan's captured baseline:

```
[   PASS] core.hooksPath                 .githooks
[   PASS] .githooks/pre-commit           matches canonical
[   PASS] .githooks/pre-push             matches canonical
[   PASS] .githooks/post-checkout        matches canonical
[   PASS] scripts/premerge.sh            matches canonical
[   PASS] scripts/token-gate.sh          matches canonical
[   PASS] scripts/premerge.conf.sh       present
[   PASS] .githooks/worktree-links.conf  present
[   PASS] scripts.prepare                sets core.hooksPath .githooks
[   PASS] scripts.verify                 bash scripts/verify-ci.sh
[   PASS] scripts.verify:static          pnpm lint && pnpm check-types
[   PASS] scripts.premerge               bash scripts/premerge.sh
[   FAIL] .husky                         legacy husky hook directory present — remove after migration
[   PASS] AGENTS.md policy               policy marker present
[   INFO] .github/workflows              no remote CI workflows

medicount: DRIFT — 1 failing check(s)
```

If any check other than the five listed `DRIFT`s and the `AGENTS.md policy` `WARN` changes status, stop — an unintended edit leaked into a file this plan did not intend to touch.

- [ ] **Step 7: Report final state — do not commit**

```bash
git status --short
git diff --stat
```

Expected: `git status --short` shows the Task 1 renames (`R`) plus modifications (`M`) to every file edited in Tasks 2-8 (including `M tests/test_token_efficient_gates.py`), the deletion (`D`) of `token-efficient-gates/assets/token-gate.sh`, and one untracked/new file (`??` or `A`) at `tests/test_lifecycle_gate_policy.py`. Nothing is committed. Present this output to the user and wait for an explicit go-ahead before running `git commit` — per this repo's `AGENTS.md`, committing is never implied by finishing the work.

---

## Self-Review

**Spec coverage:** Every row of the spec's correction table (SKILL.md ×3, agents-policy.md ×2, premerge.sh ×3, premerge.conf.sh ×1, policy-rationale.md ×2 — 11 occurrences total, matching this plan's own grep rather than the spec's "9곳" prose count) maps to a step above. The directory rename, description replacement, Boundaries rewrite, and `token-gate.sh` orphan deletion + doc pointer are each their own task. The two "Open follow-ups" in the spec (pilot reapplication timing, 3-agent symlink deployment timing) are resolved in the "Out of Scope" section, as the spec itself requires this plan to do. Beyond the spec's own scope: pre-flight baseline verification surfaced an untracked dependency (`tests/test_token_efficient_gates.py::RunnerTests` sources the file Task 8 deletes) that the spec and the original draft of this plan did not account for; Task 8 was expanded, and Task 9 gained a full-suite run, to close that gap without silently breaking test coverage.

**Placeholder scan:** No task contains "TBD", "similar to Task N", or an unshown code block — every edit shows full old/new text.

**Type consistency:** N/A (no functions/types are introduced; this is a text-content migration). The one cross-task invariant — `POLICY_MARKER` in `scripts/audit.py` (Task 6) must equal the marker line in `assets/agents-policy.md` (Task 3) — is checked explicitly in Task 9 Step 2 rather than assumed.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-lifecycle-gate-policy-rename.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

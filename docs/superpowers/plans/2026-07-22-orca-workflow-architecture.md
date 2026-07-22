# Orca Workflow Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `orca-review-gate`/`orca-sdd` with a three-skill issue-lifecycle orchestration (`orca-workflow`, `orca-task-runner`, `orca-evaluate`) per `docs/superpowers/specs/2026-07-22-orca-workflow-architecture-design.md`.

**Architecture:** `orca-workflow` is the top-level coordinator (epic/task routing, issue-drain, never generates or evaluates). `orca-task-runner` (renamed from `orca-sdd`) owns generation only — subtask fan-out across Claude Code/Codex/agy with mechanical gates. `orca-evaluate` (new, absorbs `orca-review-gate`) owns evaluation only — fresh-context diff review (no cross-model requirement) plus e2e/docker, returning PASS/FAIL/ESCALATE.

**Tech Stack:** Markdown skill files (`SKILL.md`) with YAML frontmatter, Python/pytest for structural validation, bash for `orca` CLI orchestration examples.

## Global Constraints

- Cross-model (provider-exclusion) evaluator selection is fully removed — no task in this plan may reintroduce a "generator's provider excluded from evaluator" rule.
- Evaluation happens **once per task**, never per subtask.
- Contract negotiation between `orca-task-runner` (generator) and `orca-evaluate` (evaluator) is capped at **2 rounds**; on non-convergence the generator (`orca-task-runner`) proceeds with its own proposal.
- Retry loop between `orca-evaluate` FAIL and `orca-task-runner` regeneration is capped at **N=2**; `ESCALATE` always skips retry and goes straight to the human inspection checkpoint owned by `orca-workflow`.
- `orca-workflow` never reads diff or report bodies directly — only file paths, statuses, and short results.
- Model/effort values are never hardcoded in any orca skill body — always resolved from `~/.agents/orca-workflows/model-selection.md` and `~/.agents/orca-workflows/models/{claude-code,codex,agy}.md` at launch time.
- All three new skills are self-relative (identical text regardless of which provider — Claude Code, Codex, agy — is the coordinator).

---

### Task 1: Write the skill-structure validator

**Files:**
- Create: `tests/test_orca_skills.py`

**Interfaces:**
- Consumes: nothing (pure filesystem/text checks against `skills/` and `orca-workflows/`)
- Produces: a pytest suite that later tasks must satisfy — `test_skill_directory_exists`, `test_frontmatter_has_name_and_description`, `test_retired_skill_removed`, `test_no_stale_terms_in_body`, `test_delegation_references`, `test_orca_evaluate_has_verdict_vocabulary`, `test_workflows_docs_reference_new_skill_names`

- [ ] **Step 1: Write the test file**

```python
"""Structural validation for the orca-workflow/orca-task-runner/orca-evaluate
skill family. These are prose/instruction files, not executable code, so the
checks validate structure (frontmatter, cross-references, stale-term absence)
rather than runtime behavior.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
WORKFLOWS_DIR = REPO_ROOT / "orca-workflows"

NEW_SKILLS = ["orca-workflow", "orca-task-runner", "orca-evaluate"]
RETIRED_SKILLS = ["orca-review-gate", "orca-sdd"]
STALE_TERMS = [
    "orca-review-gate",
    "orca-sdd",
    "evaluator에서 제외",
    "cross-model 리뷰 게이트",
]
WORKFLOWS_DOCS = [
    "model-selection.md",
    "models/claude-code.md",
    "models/codex.md",
    "models/agy.md",
]


def _read_skill(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    assert path.is_file(), f"{name}/SKILL.md missing"
    return path.read_text()


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "missing YAML frontmatter"
    return text.split("---\n", 2)[1]


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_skill_directory_exists(name):
    assert (SKILLS_DIR / name / "SKILL.md").is_file(), f"{name}/SKILL.md missing"


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_frontmatter_has_name_and_description(name):
    text = _read_skill(name)
    fm = _frontmatter(text)
    assert re.search(rf"^name:\s*{re.escape(name)}\s*$", fm, re.M), (
        f"{name}: frontmatter 'name' must equal directory name"
    )
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    assert desc and len(desc.group(1)) > 40, (
        f"{name}: 'description' missing or too short to carry real trigger info"
    )


@pytest.mark.parametrize("name", RETIRED_SKILLS)
def test_retired_skill_removed(name):
    assert not (SKILLS_DIR / name).exists(), (
        f"{name} must be deleted from skills/, not left alongside its replacement"
    )


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_no_stale_terms_in_body(name):
    text = _read_skill(name)
    for term in STALE_TERMS:
        assert term not in text, f"{name}: stale reference '{term}' should be gone"


def test_delegation_references():
    task_runner = _read_skill("orca-task-runner")
    workflow = _read_skill("orca-workflow")
    assert "orca-evaluate" in task_runner, (
        "orca-task-runner must hand off evaluation to orca-evaluate, not embed it"
    )
    assert "orca-task-runner" in workflow and "orca-evaluate" in workflow, (
        "orca-workflow must route to both orca-task-runner and orca-evaluate"
    )


def test_orca_evaluate_has_verdict_vocabulary():
    text = _read_skill("orca-evaluate")
    for term in ("PASS", "FAIL", "ESCALATE"):
        assert term in text, f"orca-evaluate must define the '{term}' verdict"


def test_orca_workflow_never_generates_or_evaluates_itself():
    text = _read_skill("orca-workflow")
    assert "생성하지도, 평가하지도 않는다" in text or (
        "생성" in text and "평가" in text and "않는다" in text
    ), "orca-workflow must state it never generates or evaluates directly"


@pytest.mark.parametrize("doc", WORKFLOWS_DOCS)
def test_workflows_docs_reference_new_skill_names(doc):
    text = (WORKFLOWS_DIR / doc).read_text()
    for term in RETIRED_SKILLS:
        assert term not in text, f"{doc}: stale reference '{term}'"
```

- [ ] **Step 2: Run it to confirm it fails for the right reason (red)**

Run: `cd /Users/minchul/Projects/sleeptimegrt-skills && python3 -m pytest tests/test_orca_skills.py -v`
Expected: FAIL — `orca-workflow/SKILL.md missing` (and similar) for `orca-workflow`/`orca-task-runner`/`orca-evaluate`, because none of Tasks 2–5 have run yet. This confirms the test is actually checking something, not vacuously passing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_orca_skills.py
git commit -m "test: add structural validator for orca-workflow skill family"
```

---

### Task 2: Write `orca-task-runner` (rename + rewrite from `orca-sdd`)

**Files:**
- Create: `skills/orca-task-runner/SKILL.md`
- Delete: `skills/orca-sdd/` (entire directory)
- Test: `tests/test_orca_skills.py` (subset: `test_skill_directory_exists[orca-task-runner]`, `test_frontmatter_has_name_and_description[orca-task-runner]`, `test_no_stale_terms_in_body[orca-task-runner]`)

**Interfaces:**
- Consumes: `~/.agents/orca-workflows/model-selection.md` and `models/{claude-code,codex,agy}.md` (read at launch time, paths only — no values copied into this file)
- Produces: task-level diff + resolved providers/models, handed to `orca-workflow`, which forwards it to `orca-evaluate`. Does **not** call `orca-evaluate` or `orca-review-gate` itself.

- [ ] **Step 1: Write the new skill file**

```markdown
---
name: orca-task-runner
description: Use when generating the implementation for one task (issue) — proposes an implementation-and-verification contract to orca-evaluate, then fans out subtasks across Claude Code/Codex/agy terminals in dependency-ordered waves (cap 3). Subtask gates are mechanical only (typecheck/unit test/lint/format) — never an agent reviewer; task-level review belongs to orca-evaluate. Self-relative — works identically whichever provider is the coordinator.
---

# Orca Task Runner

하나의 task(issue)를 구현한다. **생성만** 한다 — 평가는 이 스킬의 책임이 아니다(`orca-evaluate`가 담당). subtask 단위 리뷰어 역할은 두지 않는다.

## 0. 전제

- `orca status --json` ready. 실패 시 아래 "폴백".
- feature worktree에서 실행 중이어야 한다(main 체크아웃에서 금지). 워커는 전부 `--worktree active`에 생성.
- CLI 기반 coordinator(Codex/agy)는 launch 시 approval·sandbox를 명시한다. 기본 posture는 `-a never -s workspace-write`이며, 필요한 권한이 이를 넘으면 조용히 완화하지 말고 작업 범위와 권한을 다시 확인한다.
- 모델·effort는 매 launch 전 아래 문서에서 subtask 유형(전사·기계적 / 통합·판단 / 아키텍처)에 맞게 고른다. 값을 이 스킬에 복제하지 않는다.
  - `~/.agents/orca-workflows/model-selection.md`
  - `~/.agents/orca-workflows/models/claude-code.md`
  - `~/.agents/orca-workflows/models/codex.md`
  - `~/.agents/orca-workflows/models/agy.md`

## 1. Contract 제안 (generator 역할)

`orca-workflow`가 이 task를 넘기면, 코드를 쓰기 전에 **제안서**를 먼저 쓴다:

- 구현 범위(무엇을 만들 것인가, 어떤 파일을 건드릴 것인가)
- 검증 방법(구체적인 파일/함수/테스트로 — issue의 `## Acceptance criteria`를 어떻게 커버할지)

`orca-evaluate`가 이 제안을 issue의 원본 acceptance criteria에 대조해 검토한다. 반려되면 수정해서 다시 제안한다. **최대 2 라운드.** 2라운드 안에 합의가 안 되면 이 스킬(generator)이 결정권을 가지고 그 제안대로 진행한다 — evaluator의 이견은 기록에 남기되 진행을 막지 않는다.

## 2. Subtask DAG 구성

합의된 범위로 subtask를 쪼갠다. 각 subtask가 만들/수정할 파일 목록을 비교: **겹치면 `--deps` 순차 의존, 독립이면 같은 wave.** 판정이 애매하면 보수적으로 의존 처리.

```bash
orca orchestration task-create --spec "<subtask 본문 + 아래 필수 항목>" --deps '["task_xxx"]' --json
```

subtask spec 필수 항목: ①구체적 작업 내용(코드 블록 포함 그대로) ②커밋 대상 브랜치·worktree 명시 ③resolved provider/model/effort 기록 ④"막히면 ask로 blocking 질문" ⑤"완료 시 preamble 지시대로 worker_done(payload에 filesModified)" ⑥**병렬 커밋 안전 규칙**(같은 worktree 공유): `git add` 명시 경로만·`git commit -m "<msg>" -- <files>` pathspec 필수·index.lock 재시도 — 2026-07-20 #211 파일럿에서 3-워커 병렬 커밋 충돌 0 실증.

## 3. Wave 준비

wave 크기(**최대 3** — CPU 경합 실측 교훈)만큼 터미널. provider는 자유 선택(claude/codex/agy 아무거나, 토큰 효율을 위해 섞어도 됨) — 모델·effort는 subtask 성격에 맞게 provider 문서에서 고른다.

```bash
# claude
orca terminal create --worktree active --title task-impl-<n> \
  --command "claude --model <model> --effort <effort> --permission-mode bypassPermissions" --json
# codex
orca terminal create --worktree active --title task-impl-<n> \
  --command "codex --model <model> -c model_reasoning_effort=<effort> -s workspace-write -a never" --json
# agy
orca terminal create --worktree active --title task-impl-<n> \
  --command "agy -p '<subtask 지침>' --model <model> --print-timeout 15m" --json
orca terminal wait --terminal <impl-handle> --for tui-idle --timeout-ms 60000 --json   # agy는 --for exit --timeout-ms 960000
```

(구현자는 빌드·테스트 실행이 필요해 Bash 전체 허용 — worktree 격리가 전제. 권한 stall 발견 시 조합을 조정하고 이 스킬에 반영.)

## 4. Subtask 게이트 — 기계적인 것만

subtask가 worker_done을 보내기 전에 스스로 실행: typecheck, unit test, formatter, linter, 무거운 환경 구성이 필요 없는 script test. **subtask 단위 agent 리뷰어는 없다.** 게이트를 통과하지 못하면 worker_done을 보내지 않고 스스로 고친다.

## 5. Wave 루프

```bash
orca orchestration task-list --ready --brief --json
orca orchestration dispatch --task <task_id> --to <impl_handle> --inject --json   # 최대 3 병렬
```

- ⚠️ **`check --wait` 단독 대기 금지** (2026-07-20 #211 파일럿 실측): coordinator가 Orca 터미널 내부 세션이면 worker_done이 check 큐로 안 잡힐 수 있다(task 상태는 정상 갱신됨). 기본 대기 = `task-list --brief --json` 상태 폴링 또는 커밋/파일 존재 감시(20-30s 간격), `check --wait`는 보조.
- timeout·`count:0` = 체크포인트. `terminal read`로 생사 확인, 활동 중이면 계속 대기.
- decision_gate(워커 ask) → 판단 가능하면 `reply`, 불가하면 `orca-workflow`에 에스컬레이션.
- worker_done 유실 복구: 커밋/산출물 확인 + `task-update --status completed` 수동 복구, 기록.

## 6. 완료

전 subtask 완료 → task 전체 diff를 정리해 `orca-workflow`에 반환한다(diff 경로 + resolved providers/models + wave 구성 기록). **`orca-evaluate`는 이 스킬이 직접 호출하지 않는다** — `orca-workflow`가 호출한다.

## 폴백

- orca 런타임 불가: `superpowers:subagent-driven-development`로 폴백 — 모델은 provider 문서의 같은 subtask 유형 등급을 Agent tool `model` 인자로. 폴백 발동은 사용자에게 보고.
```

- [ ] **Step 2: Remove the retired skill directory**

```bash
git rm -r skills/orca-sdd
```

- [ ] **Step 3: Run the validator subset to confirm this task's pieces are correct**

Run: `python3 -m pytest "tests/test_orca_skills.py::test_skill_directory_exists[orca-task-runner]" "tests/test_orca_skills.py::test_frontmatter_has_name_and_description[orca-task-runner]" "tests/test_orca_skills.py::test_no_stale_terms_in_body[orca-task-runner]" "tests/test_orca_skills.py::test_retired_skill_removed[orca-sdd]" -v`
Expected: all 4 PASS. (Note: parametrize IDs use hyphens — `orca-task-runner`, not `orca_task_runner` — a plain `-k` substring won't match; exact node IDs are used here instead. `orca-review-gate`/`orca-workflow`/`orca-evaluate` cases are intentionally not run yet — later tasks.)

- [ ] **Step 4: Commit**

```bash
git add skills/orca-task-runner
git commit -m "feat: rename orca-sdd to orca-task-runner, scope to generation only"
```

---

### Task 3: Write `orca-evaluate` (new — absorbs `orca-review-gate`)

**Files:**
- Create: `skills/orca-evaluate/SKILL.md`
- Delete: `skills/orca-review-gate/` (entire directory)
- Test: `tests/test_orca_skills.py` (subset: `orca-evaluate` cases, `test_orca_evaluate_has_verdict_vocabulary`, `test_retired_skill_removed[orca-review-gate]`)

**Interfaces:**
- Consumes: task diff path + issue's `## Acceptance criteria` (from `orca-workflow`); contract proposal file path (from `orca-task-runner`, relayed by `orca-workflow`)
- Produces: one of `PASS` / `FAIL` (with severity-tagged findings) / `ESCALATE` (with reason) — returned to `orca-workflow`, never dispatches retries itself

- [ ] **Step 1: Write the new skill file**

```markdown
---
name: orca-evaluate
description: Use when evaluating a completed task's diff before merge — reviews the orca-task-runner implementation contract against the issue's Acceptance criteria, runs a fresh-context code review (same provider is fine, no cross-model requirement) plus e2e/docker tests, and returns PASS, FAIL-with-feedback, or ESCALATE. Self-relative.
---

# Orca Evaluate

task(issue) 하나를 **1회** 평가한다(subtask마다 하지 않음). 코드를 쓰지 않는다 — `orca-task-runner`가 생성한 결과만 판단한다.

## 왜 cross-model이 아닌가

이전 설계는 evaluator가 생성자와 다른 provider여야 한다고 강제했다. 지금은 그 규칙을 버렸다 — Claude Code의 `/advisor`가 **같은 provider**로도 self-review 편향을 깨는 데 효과가 있다는 것이 근거다. self-review 문제를 깨는 진짜 레버는 provider가 다른 게 아니라 **다른 세션(fresh context) + skeptical하게 튜닝된 프롬프트**다. evaluator는 어떤 provider든 상관없다 — coordinator·generator와 별도 세션이기만 하면 된다.

## 1. Contract 검토 (evaluator 역할)

`orca-task-runner`가 구현 전 제안서(범위 + 검증 방법)를 보내오면, **issue의 원본 `## Acceptance criteria`에 대조해서** 검토한다. 판단 기준은 "제안이 그럴듯한가"가 아니라 "acceptance criteria를 실제로 커버하는가"다. 부족하면 구체적으로 반려(어느 criteria가 안 커버되는지 명시). 최대 2라운드까지 왕복하고, 그 안에 합의 안 되면 generator가 결정권을 가진다 — 이견은 기록만 하고 진행을 막지 않는다.

`## Acceptance criteria`가 issue body에 없으면 평가를 진행하지 않고 `orca-workflow`에 보고한다. (issue 생성 시 이 섹션을 보장하는 절차는 아직 없다 — 별도 후속 이슈. 임시로는 `/triage` 리다이렉트 대상으로 취급한다.)

## 2. Diff 리뷰

```bash
git diff "$(git merge-base origin/main HEAD)"...HEAD > <worktree 루트>/.evaluate-diff.patch
```

fresh-context 리뷰어 terminal을 하나 만든다(coordinator·generator와 별도 세션 — provider는 자유, 보통 launch 비용이 가장 싼 provider). 리뷰어는 반드시 이 두 가지를 갖는다: ①skeptical 지침("동의 표명 불필요, 결함·spec-divergence만 보고, 근거 있는 우려를 안이하게 넘기지 말 것") ②issue의 acceptance criteria 원문.

```bash
orca terminal create --worktree active --title eval-review \
  --command "<provider의 launch 문법 — provider 문서에서 resolve>" --json
orca terminal wait --terminal <review-handle> --for tui-idle --timeout-ms 60000 --json
orca orchestration task-create --spec "<diff 절대경로 + acceptance criteria 원문 + skeptical 리뷰 지침 + report 경로 + 코드 수정 금지>" --json
orca orchestration dispatch --task <task_id> --to <review-handle> --inject --json
```

report는 severity(Critical/Important/Minor) + 도달 조건 + 최악 결과 + fail-closed 여부를 포함해야 한다.

## 3. e2e/docker 통합 테스트

코드 리뷰와 별개로, 실제 실행이 필요한 테스트를 돌린다(e2e, docker 기반 통합 테스트, agent가 앱을 직접 조작하는 e2e 포함). 로그가 크므로 **별도 terminal에서 실행하고 결과(exit code + 로그 경로)만 받는다** — coordinator·evaluator 컨텍스트에 로그 본문을 붙이지 않는다.

```bash
orca terminal create --worktree active --title eval-e2e \
  --command "bash -lc '<repo의 e2e/통합 테스트 커맨드> > <worktree 루트>/.evaluate-e2e.log 2>&1; echo EXIT:$?'" --json
orca terminal wait --terminal <e2e-handle> --for exit --timeout-ms 1800000 --json
```

## 4. 종합 판정

diff 리뷰 report + e2e 결과를 종합해 셋 중 하나로 판정한다:

- **PASS** — Critical/Important finding 없음, e2e 통과.
- **FAIL** — 구체적 finding(severity+근거) + 수정 방향을 `orca-workflow`에 반환한다. (재시도는 `orca-workflow`가 관리한다 — 이 스킬은 재-dispatch하지 않는다.)
- **ESCALATE** — 다음 중 하나면 재시도 없이 즉시: acceptance criteria 자체가 애매해서 판정이 불가능, 구현이 issue 스코프 밖의 것을 건드림, e2e가 인프라 문제(계정·secret·환경)로 판단 불가.

## 폴백

- orca 런타임 불가: 리뷰어를 orca 없이 **Bash로 직접**(headless) 실행해 diff 리뷰·report 회수. e2e는 로컬에서 직접 실행하고 로그 경로만 기록. 폴백 발동은 사용자에게 보고.
```

- [ ] **Step 2: Remove the retired skill directory**

```bash
git rm -r skills/orca-review-gate
```

- [ ] **Step 3: Run the validator subset**

Run: `python3 -m pytest "tests/test_orca_skills.py::test_skill_directory_exists[orca-evaluate]" "tests/test_orca_skills.py::test_frontmatter_has_name_and_description[orca-evaluate]" "tests/test_orca_skills.py::test_no_stale_terms_in_body[orca-evaluate]" tests/test_orca_skills.py::test_orca_evaluate_has_verdict_vocabulary "tests/test_orca_skills.py::test_retired_skill_removed[orca-review-gate]" -v`
Expected: all 5 PASS. (Exact node IDs again — parametrize values use hyphens, not underscores.)

- [ ] **Step 4: Commit**

```bash
git add skills/orca-evaluate
git commit -m "feat: add orca-evaluate, absorbing orca-review-gate; drop cross-model requirement"
```

---

### Task 4: Write `orca-workflow` (new top-level coordinator)

**Files:**
- Create: `skills/orca-workflow/SKILL.md`
- Test: `tests/test_orca_skills.py` (subset: `orca-workflow` cases, `test_delegation_references`, `test_orca_workflow_never_generates_or_evaluates_itself`)

**Interfaces:**
- Consumes: `gh issue view`/`gh issue list` output; calls `orca-task-runner` (generate) and `orca-evaluate` (evaluate) by name
- Produces: merge decision, or a human-facing "inspecting" report; owns the retry counter (max 2) and the epic task-queue

- [ ] **Step 1: Write the new skill file**

```markdown
---
name: orca-workflow
description: Use when picking up a GitHub issue and driving it through its full lifecycle — branches on issue type (epic vs task), runs issue-drain validation for epics, builds an issue-graph task-queue, and for each task relays the orca-task-runner/orca-evaluate contract negotiation, routes PASS/FAIL/ESCALATE, and escalates to a human inspection checkpoint. Never generates or evaluates code directly — pure orchestration, kept context-light. Use for "이슈 가져와", "이슈 처리해", "epic 실행해" style requests. Self-relative.
---

# Orca Workflow

GitHub issue 하나를 받아 끝까지(merge까지) 가져가는 최상위 오케스트레이터다. **코드를 생성하지도, 평가하지도 않는다** — 그 일은 각각 `orca-task-runner`, `orca-evaluate`가 한다. 이 스킬의 컨텍스트에는 issue 번호·task 상태·짧은 판정 결과만 남긴다. diff나 report 본문을 직접 읽지 않는다.

## 0. 전제

- `orca status --json` ready. 실패 시 아래 "폴백".
- `gh issue view <num>`으로 issue 타입 확인(label 또는 body 구조로 epic/task 판별).
- CLI 기반 coordinator(Codex/agy)는 launch 시 approval·sandbox를 명시한다. 기본 posture는 `-a never -s workspace-write`.

## 1. Epic 경로

**1a. issue-drain** — 별도 subagent(이 세션과 다른, 별도로 뜬 세션)에게 child issue 전체 검증을 맡긴다:

- 각 child issue가 self-contained한지(`## What to build` + `## Acceptance criteria`)
- `Blocked by` / `Refs` 관계가 실제로 존재하고 방향이 맞는지
- 그래프상 빠진 child나 순환 의존이 없는지

```bash
gh issue view <epic-num> --json body,title
gh issue list --search "epic:<epic-num> in:body" --json number,title,body   # 또는 epic body에 나열된 child 번호 파싱
```

검증 실패 → 사용자에게 보고하고 멈춘다(수정 후 재호출). 통과 → **1b**.

**1b. task-queue 확정** — child issue 그래프(`Blocked by`/`Refs`/epic body 나열 순서)로 실행 순서를 정한다. file-overlap이 아니라 **issue 그래프 기준**이다(구현 전이라 파일 목록을 아직 모른다).

**1c. 순회** — ready task마다 아래 "2. Task 경로"를 실행. 완료되면 dequeue하고 의존이 풀린 다음 task로 진행. 전 task 완료 → epic 종료 보고.

## 2. Task 경로

**2a. Contract 협상 relay** — `orca-task-runner`를 "제안서 작성" 모드로 호출 → 나온 제안서 파일 경로를 `orca-evaluate`에 "검토" 모드로 전달 → 반려면 파일 경로를 다시 `orca-task-runner`에 전달. **파일 내용은 읽지 않고 경로만 중계**한다. 최대 2라운드, 그 이후는 `orca-task-runner`가 결정권을 가지고 진행(그대로 2b로 넘어감).

**2b. Generate** — `orca-task-runner` 호출, task 전체 diff 경로를 결과로 받는다.

**2c. Evaluate** — `orca-evaluate` 호출(diff 경로 전달), PASS / FAIL / ESCALATE 중 하나를 결과로 받는다.

**2d. 라우팅**:
- PASS → merge 진행(squash), task 종료.
- FAIL → 재시도 카운터 확인. **2회 미만이면** feedback과 함께 `orca-task-runner`에 재-dispatch(2b로). **2회 도달하면** inspecting으로.
- ESCALATE → 재시도 카운트 무관하게 즉시 inspecting.

## 3. Inspecting

사람 체크포인트. 보고 내용: issue 번호, PASS/FAIL/ESCALATE 판정 근거, 재시도 횟수, resolved providers/models. 사람이 고를 수 있는 것: 계속(피드백 반영해 재시도) / 재계획(요구사항 자체를 다시 논의 — 1a 또는 issue 수정으로 복귀) / 중단.

## 폴백

- orca 런타임 불가: transport만 우회 — `orca-task-runner`/`orca-evaluate`의 폴백 규칙을 그대로 따르며, 이 스킬은 두 결과를 이어주는 역할만 계속한다.
- 폴백 발동은 항상 사용자에게 보고한다.
```

- [ ] **Step 2: Run the validator subset**

Run: `python3 -m pytest "tests/test_orca_skills.py::test_skill_directory_exists[orca-workflow]" "tests/test_orca_skills.py::test_frontmatter_has_name_and_description[orca-workflow]" "tests/test_orca_skills.py::test_no_stale_terms_in_body[orca-workflow]" tests/test_orca_skills.py::test_delegation_references tests/test_orca_skills.py::test_orca_workflow_never_generates_or_evaluates_itself -v`
Expected: all 5 PASS. (Exact node IDs again — parametrize values use hyphens, not underscores.)

- [ ] **Step 3: Commit**

```bash
git add skills/orca-workflow
git commit -m "feat: add orca-workflow top-level issue-lifecycle coordinator"
```

---

### Task 5: Update `orca-workflows/` reference docs — remove cross-model language and stale skill names

**Files:**
- Modify: `orca-workflows/model-selection.md`
- Modify: `orca-workflows/models/claude-code.md`
- Modify: `orca-workflows/models/codex.md`
- Modify: `orca-workflows/models/agy.md`
- Test: `tests/test_orca_skills.py::test_workflows_docs_reference_new_skill_names`

**Interfaces:**
- Consumes: nothing new
- Produces: provider docs that no longer imply a cross-model evaluator requirement, and no longer name the retired `orca-review-gate`/`orca-sdd` skills

- [ ] **Step 1: Edit `model-selection.md`**

Find this line:
```
Workflow orchestration (review gate, evaluator count, SDD waves, generator≠evaluator)은 `orca-review-gate`와 `orca-sdd`가 관리한다.
```
Replace with:
```
Workflow orchestration (issue-drain, contract 협상, evaluate 판정, task-runner wave 구성)은 `orca-workflow`·`orca-task-runner`·`orca-evaluate`가 관리한다.
```

- [ ] **Step 2: Edit `models/claude-code.md`**

Find this line:
```
⚠️ 저자가 Anthropic이면 Claude는 cross-model 리뷰 게이트의 evaluator에서 제외한다(self-review 회피) — 게이트 절차는 `orca-review-gate` 스킬.
```
Replace with:
```
evaluator로도 쓸 수 있다 — cross-model 강제 없음, fresh-context 원칙은 `orca-evaluate` 스킬 참조.
```

- [ ] **Step 3: Edit `models/codex.md`**

Find this frontmatter description line:
```
description: Codex(OpenAI) 모델·effort 용도 — coordinator·구현 워커, 그리고 다른 provider가 저자인 코드의 cross-model evaluator
```
Replace with:
```
description: Codex(OpenAI) 모델·effort 용도 — coordinator·구현 워커·evaluator 어디에나 쓸 수 있음(cross-model 강제 없음)
```

Find this body line:
```
`gpt-5.6-*` 계열. coordinator·구현 워커로 쓰거나, 저자 provider가 Codex/OpenAI가 아닐 때 cross-model evaluator로 쓴다(자기 provider가 저자인 리뷰에는 evaluator로 쓰지 않는다 — self-review 회피, 규칙은 `orca-review-gate` 스킬).
```
Replace with:
```
`gpt-5.6-*` 계열. coordinator·구현 워커·evaluator 어디에나 쓴다. evaluator로 쓸 때는 fresh-context(별도 세션)이기만 하면 되고 provider가 같아도 된다 — 원칙은 `orca-evaluate` 스킬.
```

- [ ] **Step 4: Edit `models/agy.md`**

Find this frontmatter description line:
```
description: agy(Gemini/Google) 모델·effort 용도 — coordinator·구현 워커, 그리고 quota 넉넉한 세 번째 cross-model 시각(evaluator)
```
Replace with:
```
description: agy(Gemini/Google) 모델·effort 용도 — coordinator·구현 워커·evaluator 어디에나 쓸 수 있음, quota가 넉넉해 적합한 작업엔 우선 고려
```

Find this line:
```
quota·오류로 호출이 skip될 수 있다 — 그때의 대체 처리는 `orca-review-gate` 스킬이 소유한다.
```
Replace with:
```
quota·오류로 호출이 skip될 수 있다 — 그때의 대체 처리는 `orca-evaluate`/`orca-task-runner` 스킬의 폴백 절이 소유한다.
```

- [ ] **Step 5: Run the validator**

Run: `python3 -m pytest tests/test_orca_skills.py::test_workflows_docs_reference_new_skill_names -v`
Expected: all 4 parametrized cases PASS.

- [ ] **Step 6: Commit**

```bash
git add orca-workflows
git commit -m "docs: drop cross-model language from orca-workflows provider guides"
```

---

### Task 6: Full validator run (green)

**Files:**
- Test: `tests/test_orca_skills.py` (full suite)

**Interfaces:**
- Consumes: everything from Tasks 1–5
- Produces: a fully green suite — the gate for moving on to deployment

- [ ] **Step 1: Run the full suite**

Run: `cd /Users/minchul/Projects/sleeptimegrt-skills && python3 -m pytest tests/test_orca_skills.py -v`
Expected: all tests PASS (0 failed).

- [ ] **Step 2: If anything fails, fix inline and re-run**

Do not proceed to Task 7 until this is fully green.

---

### Task 7: Deploy the SSoT to the three agents

**Files:**
- Modify (filesystem, outside the repo): `~/.agents/skills/*`, `~/.agents/orca-workflows` (symlinks), `~/.claude/skills/*`, `~/.gemini/config/skills/*` (symlinks), `~/.codex/skills/*` (real-file copies — Codex's symlink support is unverified as of this plan)

**Interfaces:**
- Consumes: `skills/orca-workflow`, `skills/orca-task-runner`, `skills/orca-evaluate`, `orca-workflows/` from this repo
- Produces: working, current skills for Claude Code, Codex, and agy — no agent should still see `orca-review-gate` or `orca-sdd`

- [ ] **Step 1: Remove stale symlinks and retarget the shared pool**

```bash
rm -f ~/.agents/skills/orca-review-gate ~/.agents/skills/orca-sdd
REPO=/Users/minchul/Projects/sleeptimegrt-skills
ln -sfn "$REPO/skills/orca-workflow" ~/.agents/skills/orca-workflow
ln -sfn "$REPO/skills/orca-task-runner" ~/.agents/skills/orca-task-runner
ln -sfn "$REPO/skills/orca-evaluate" ~/.agents/skills/orca-evaluate
```

- [ ] **Step 2: Retarget Claude Code's symlinks**

```bash
rm -f ~/.claude/skills/orca-review-gate ~/.claude/skills/orca-sdd
ln -sfn ../../.agents/skills/orca-workflow ~/.claude/skills/orca-workflow
ln -sfn ../../.agents/skills/orca-task-runner ~/.claude/skills/orca-task-runner
ln -sfn ../../.agents/skills/orca-evaluate ~/.claude/skills/orca-evaluate
```

- [ ] **Step 3: Retarget agy's symlinks**

```bash
rm -f ~/.gemini/config/skills/orca-review-gate ~/.gemini/config/skills/orca-sdd
ln -sfn ../../../.agents/skills/orca-workflow ~/.gemini/config/skills/orca-workflow
ln -sfn ../../../.agents/skills/orca-task-runner ~/.gemini/config/skills/orca-task-runner
ln -sfn ../../../.agents/skills/orca-evaluate ~/.gemini/config/skills/orca-evaluate
```

- [ ] **Step 4: Update Codex's real-file copies**

```bash
rm -rf ~/.codex/skills/orca-review-gate ~/.codex/skills/orca-sdd
mkdir -p ~/.codex/skills/orca-workflow ~/.codex/skills/orca-task-runner ~/.codex/skills/orca-evaluate
cp "$REPO/skills/orca-workflow/SKILL.md" ~/.codex/skills/orca-workflow/SKILL.md
cp "$REPO/skills/orca-task-runner/SKILL.md" ~/.codex/skills/orca-task-runner/SKILL.md
cp "$REPO/skills/orca-evaluate/SKILL.md" ~/.codex/skills/orca-evaluate/SKILL.md
```

- [ ] **Step 5: Verify no stale skill directories remain anywhere**

```bash
find ~/.claude/skills ~/.codex/skills ~/.gemini/config/skills ~/.agents/skills -maxdepth 1 \( -iname "orca-review-gate" -o -iname "orca-sdd" \)
```
Expected: no output.

```bash
diff "$REPO/skills/orca-workflow/SKILL.md" ~/.codex/skills/orca-workflow/SKILL.md && \
diff "$REPO/skills/orca-task-runner/SKILL.md" ~/.codex/skills/orca-task-runner/SKILL.md && \
diff "$REPO/skills/orca-evaluate/SKILL.md" ~/.codex/skills/orca-evaluate/SKILL.md && \
echo "codex copies match SSoT"
```
Expected: `codex copies match SSoT`, no diff output above it.

- [ ] **Step 6: Retarget `orca-workflows`**

Already a symlink from earlier work (`~/.agents/orca-workflows` → `$REPO/orca-workflows`) — no action needed, just confirm:

```bash
readlink -f ~/.agents/orca-workflows/model-selection.md
```
Expected: resolves to `$REPO/orca-workflows/model-selection.md`.

_(No commit in this task — it only touches files outside the repo.)_

---

### Task 8: Final repo commit and push

**Files:**
- None new — this task just confirms everything from Tasks 1–6 is committed.

- [ ] **Step 1: Confirm clean status**

```bash
cd /Users/minchul/Projects/sleeptimegrt-skills && git status --short
```
Expected: empty (everything from Tasks 1–6 already committed per-task).

- [ ] **Step 2: Push**

```bash
git push origin main
```

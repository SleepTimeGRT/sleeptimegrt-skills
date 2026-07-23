---
name: orca-evaluate
description: Use when evaluating a completed task's diff before merge — reviews the orca-task-runner implementation contract against the issue's Acceptance criteria, runs a fresh-context code review plus e2e/docker tests, and returns PASS, FAIL-with-feedback, or ESCALATE. Self-relative.
---

# Orca Evaluate

task(issue) 하나를 **1회** 평가한다(subtask마다 하지 않음). 코드를 쓰지 않는다 — `orca-task-runner`가 생성한 결과만 판단한다.

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

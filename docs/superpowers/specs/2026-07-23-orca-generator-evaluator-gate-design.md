# Orca Generator/Evaluator Gate Rewiring — Design

**Date**: 2026-07-23
**Status**: Implemented — `skills/orca-task-runner/SKILL.md`, `skills/orca-workflow/SKILL.md`, `skills/orca-evaluate/SKILL.md`, `orca-workflows/model-selection.md`

## Context

`orca-evaluate`가 계속 확장되면서(2026-07-23 세션 중 pgTAP·agent e2e·모델 배정 논의) 실제로는 세 가지 다른 성격의 일이 한 스킬에 뭉쳐 있었다: ①code generator와의 sprint contract 협상, ②test gate 실행, ③code review. 이 셋을 비용 티어(저렴/중간/비쌈)로 재배선하고, gate 실행 책임을 generator(`orca-task-runner`)와 evaluator(`orca-evaluate`) 사이에 다시 나누는 것이 이 설계의 목적이다.

핵심 관찰:
- `orca-task-runner`의 기존 subtask 게이트(typecheck/unit test/lint/format)는 **subtask 단위**로만 돈다. 같은 wave 안에서 병렬 실행되는 형제 subtask의 커밋을 놓칠 수 있어(race), 어떤 subtask의 게이트 통과도 "task 전체가 합쳐진 뒤"를 보장하지 않는다.
- e2e·pgTAP처럼 무거운 통합 테스트는 지금까지 `orca-evaluate`가 돌렸는데, 이건 결정론적 검증이라 굳이 비싼 evaluate 단계까지 미룰 이유가 없다 — generator가 스스로 통과시킨 뒤 넘기는 게 cost-ordered fail-fast에 맞는다.
- agent e2e(Playwright로 앱을 직접 조작)는 코드 리뷰보다 먼저 끝나야 그 결과를 code review의 입력으로 쓸 수 있다.

참조: [`2026-07-22-orca-workflow-architecture-design.md`](2026-07-22-orca-workflow-architecture-design.md) (기존 3-스킬 구조와 contract 협상 프로토콜의 근거 문서 — 이 설계는 그 위에 얹는 것이지 대체하는 게 아니다), `skills/remote-ci-economics/SKILL.md` (E2E/pgTAP을 "무겁지만 로컬 재현 가능한 검증"으로 분류하는 동일한 cost-tiering 원리).

## Glossary

기존 문서([`2026-07-22-orca-workflow-architecture-design.md`](2026-07-22-orca-workflow-architecture-design.md))의 정의를 그대로 따른다. 추가:

| 용어 | 정의 |
|---|---|
| task-레벨 게이트 | subtask 전부가 끝나 하나로 합쳐진 diff 기준으로 `orca-task-runner`가 한 번 더 도는 게이트(신규) |
| GATE_FAIL | task-레벨 게이트가 재시도 한도 내에 통과 못했을 때 `orca-task-runner`가 `orca-evaluate`를 아예 부르지 않고 `orca-workflow`에 직접 반환하는 결과 값. `orca-evaluate`가 내리는 `FAIL`과는 발생 지점이 다르다(전자는 기계적 게이트, 후자는 code-reviewer 판단). |
| coding agent | `orca-evaluate`가 contract 판정·code review처럼 실제 코딩 판단이 필요한 순간에 스폰하는, High Risk tier의 강한 reasoning 모델 세션. evaluator 세션 자체(기본 agy/Gemini)와는 별도 세션. |

## A. 책임 분리 (cost-tiered)

| 티어 | 게이트 | 담당 | 실패 시 |
|---|---|---|---|
| 저렴 | typecheck/unit test/lint/format (subtask 단위) | `orca-task-runner` §4 (기존, 변경 없음) | subtask가 스스로 고침 — 무한, 한도 없음(기존 그대로) |
| 저렴 | typecheck/unit test/lint/format 재실행 (task 전체, **신규**) | `orca-task-runner`, 신규 섹션 | 자가치유 시도, **재시도 한도 2회** |
| 중간 | e2e/pgTAP (**신규 — `orca-evaluate`에서 이관**) | `orca-task-runner`, 위와 같은 섹션·같은 재시도 한도 공유 | 위와 동일 |
| 비쌈 | agent e2e | `orca-evaluate`(agy/Gemini 세션 자체, 기존 유지) | evaluate의 FAIL/ESCALATE 경로로 |
| 비쌈 | code review (agent e2e 결과를 입력으로 받음, **순서 변경**) | `orca-evaluate`가 스폰하는 coding agent | evaluate의 FAIL/ESCALATE 경로로 |
| — | contract 검토 | `orca-evaluate`가 스폰하는 coding agent(변경 없음) | 기존 2라운드 relay 그대로 |

## B. `orca-task-runner` — 신규 "Task 레벨 게이트" 섹션

위치: 기존 §5(Wave 루프) 이후, §6(완료: diff 반환) 이전.

내용:
- typecheck/unit test/lint/format을 **task 전체(모든 subtask가 합쳐진) diff 기준으로 재실행**.
- e2e·pgTAP 실행 — 둘 다 결정론적 bash, 모델 개입 없음. (지금 `orca-evaluate` §3에 있는 커맨드 패턴 — `pg_prove` exit code + `not ok` grep 등 — 을 그대로 이 섹션으로 옮긴다.)
- 실패 시: subtask 게이트와 같은 방식으로 스스로 고치고 재시도하되, **재시도 한도 2회**(기존 `orca-workflow` §2d의 evaluate-FAIL 재시도 한도와 같은 숫자로 맞춰 일관성 유지 — 임의로 다른 숫자를 고를 이유가 없다는 판단, 필요하면 조정 가능).
- 한도 도달 시: `orca-evaluate`를 호출하지 않고 `orca-workflow`에 **`GATE_FAIL`**을 직접 반환한다. 기계적으로도 안 돌아가는 코드를 비싼 evaluate 단계(agent e2e·code review)에 태울 이유가 없다.

## C. `orca-workflow` — `GATE_FAIL` 라우팅 추가

- §2b(Generate)의 반환값이 diff 경로 대신 `GATE_FAIL`일 수 있다.
- `GATE_FAIL` → §2c(Evaluate)를 건너뛰고 **바로 §3 Inspecting**으로 간다. `orca-task-runner`가 이미 자기 재시도 예산(2회)을 다 썼으므로, `orca-workflow`가 그 위에 추가로 재시도를 걸지 않는다(이중 카운팅 방지).
- Inspecting 보고 내용에 "evaluate 호출 안 됨(GATE_FAIL) — 기계적 게이트 실패"를 명시해, evaluate의 code-quality FAIL/ESCALATE와 사람이 구분할 수 있게 한다.

## D. `orca-evaluate` 변경

1. §3에서 e2e/pgTAP을 완전히 제거한다 — **agent e2e만 남는다**. e2e/pgTAP 데이터는 이제 이 스킬에 아예 들어오지 않는다(전량 신뢰, 재검증 없음 — task-runner가 이미 게이트로 걸렀으므로).
2. **실행 순서 변경**: agent e2e를 먼저 돌리고, 그 결과(무엇을 했고 무엇이 실패했는지 자연어 요약)를 §2 code-reviewer 스폰 시 diff·acceptance criteria와 **함께** task spec에 넣는다. code review가 "diff는 멀쩡해 보이지만 agent e2e에서 특정 동작이 실패했다"는 교차 정보를 갖고 판단할 수 있게 하기 위해서다.
   - 트레이드오프: agent e2e와 code review가 순차 실행되어(기존엔 사실상 독립적으로 병렬 가능했음) wall-clock이 늘어난다. 단순성을 우선한 v1 선택 — 나중에 "병렬로 돌리고 code review에 늦게 주입" 형태로 최적화할 여지는 남겨둔다.
3. §4 리포트 합성은 이제 **contract 판정 + code-reviewer report(agent e2e 결과가 이미 반영됨) + agent e2e 자기 요약**만 합친다. e2e/pgTAP 언급은 사라진다(task-runner 쪽 리포트로 완전히 이관).

## E. 변경 없음

- Contract 검토(§1) — 여전히 coding agent를 스폰해 판단, evaluator 세션(Gemini) 자체는 relay만.
- `orca-workflows/model-selection.md`의 Computer Use/Long-Context 축과 그 예외 규칙(code review·contract 판단은 이 축에서 제외, High Risk tier 고정) — 그대로 유지.
- `orca-workflow`의 나머지 라우팅(PASS/FAIL/ESCALATE, 재시도 2회, Inspecting 3분기)은 변경 없음. `GATE_FAIL`은 그 위에 추가되는 네 번째 갈래일 뿐이다.

## 영향받는 파일

- `skills/orca-task-runner/SKILL.md` — 신규 "Task 레벨 게이트" 섹션 추가.
- `skills/orca-workflow/SKILL.md` — §2b/§2d에 `GATE_FAIL` 분기 추가.
- `skills/orca-evaluate/SKILL.md` — §3에서 e2e/pgTAP 제거, agent e2e ↔ code review 순서 변경, §4 리포트 구성 요소 수정.

`orca-workflows/model-selection.md`, `orca-workflows/models/agy.md`는 이번 재배선으로 내용이 틀리지 않는다(둘 다 이미 e2e/pgTAP을 "모델 불필요"로 취급하고 있었으므로) — 수정 불필요, 확인만 하면 된다.

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

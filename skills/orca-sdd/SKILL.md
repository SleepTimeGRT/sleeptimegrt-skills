---
name: orca-sdd
description: Use when executing an SDD implementation plan — registers plan tasks as an Orca orchestration DAG with file-overlap dependencies, dispatches implementer workers in parallel waves (cap 3), and reviews every task cross-model (never same-provider) before merge, finishing with the orca-review-gate skill. Self-relative — works identically whichever provider (Claude Code, Codex, agy) is the coordinator. Replaces subagent-only SDD dispatch.
---

# Orca SDD 실행

SDD 플랜의 워커 dispatch를 orca orchestration으로 실행한다. SDD 프로토콜(task별 구현→리뷰, 플랜 대비 검증)은 기존과 동일 — transport만 orca. 범용 lifecycle 규율은 `orchestration` 스킬, task 리뷰의 evaluator 선택 규칙과 최종 게이트는 `orca-review-gate` 스킬을 그대로 재사용한다.

이 스킬은 **self-relative**하다 — Claude Code·Codex·agy 중 어느 쪽이 coordinator든 같은 텍스트로 동작한다. coordinator/generator/evaluator 역할 구분은 `orca-review-gate`와 동일하다 — **coordinator는 조율만 하고 파일을 직접 편집하지 않는다.** 구현 worker(generator)는 매 wave마다 별도 terminal이고, coordinator 자신의 provider를 기본으로 쓰되(가장 저렴) 다른 provider도 선택할 수 있다(self-review 문제는 *평가*에만 적용되지 구현에는 적용되지 않는다 — 이건 coordinator가 무엇이든 동일). 반면 **task 리뷰는 항상 cross-model**이다 — 구현자(generator)와 같은 provider로 리뷰하지 않는다. 이게 이 스킬의 핵심 정책이며, 최종 `orca-review-gate` 한 번으로 cross-model 검증을 미루는 방식이 아니다: task 단위부터 이미 cross-model이라 결함을 조기에 잡고, 최종 게이트는 task 리뷰가 못 보는 **통합(cross-task) 이슈**를 잡는 별도 층으로 남는다.

coordinator가 직접 편집하지 않는 이유는 `orca-review-gate`와 같다 — 코드 생성을 전부 별도 generator terminal로 밀어내야 coordinator 컨텍스트가 wave·task 수에 비례해 불어나지 않는다. DAG 구성 시 coordinator가 쓰는 텍스트(task spec)는 플랜 본문을 그대로 옮기는 수준이라 가볍다 — 이건 code generation이 아니라 orchestration 메타데이터다.

## 0. 전제

- `orca status --json` ready. 실패 시 아래 "폴백".
- coordinator는 **feature worktree**에서 실행 중이어야 한다 (main 체크아웃에서 SDD 금지). 워커는 전부 `--worktree active`에 생성 — cwd가 구조적으로 격리된다.
- CLI 기반 coordinator(Codex/agy)는 launch 시 approval·sandbox를 명시한다. 기본 posture는 `-a never -s workspace-write`이며, 필요한 권한이 이를 넘으면 조용히 완화하지 말고 작업 범위와 권한을 다시 확인한다.
- 모델·effort는 매 launch 전에 아래 문서에서 task 유형(전사·기계적 / 통합·판단 / 아키텍처 / task 리뷰)에 맞게 고른다. 값을 이 스킬에 복제하지 않는다.
  - `~/.agents/orca-workflows/model-selection.md`
  - `~/.agents/orca-workflows/models/claude-code.md`
  - `~/.agents/orca-workflows/models/codex.md`
  - `~/.agents/orca-workflows/models/agy.md`

## 1. DAG 구성

- 플랜의 각 task가 만들/수정할 파일 목록을 비교: **겹치면 `--deps` 순차 의존, 독립이면 같은 wave**. 판정이 애매하면 보수적으로 의존 처리.

```bash
orca orchestration task-create --spec "<플랜 task 전문 + 아래 필수 항목>" --deps '["task_xxx"]' --json
```

- task spec 필수 항목: ①플랜 task 본문(코드 블록 포함 그대로) ②커밋 대상 브랜치·worktree 명시 ③resolved provider/model/effort 기록 ④"막히면 ask로 blocking 질문" ⑤"완료 시 preamble 지시대로 worker_done(payload에 filesModified)" ⑥**병렬 커밋 안전 규칙**(같은 worktree 공유): `git add` 명시 경로만·`git commit -m "<msg>" -- <files>` pathspec 필수·index.lock 재시도 — 2026-07-20 #211 파일럿에서 3-워커 병렬 커밋 충돌 0 실증.

## 2. 워커 준비

**구현자(generator)** — wave 크기(**최대 3** — CPU 경합 실측 교훈)만큼 터미널. 항상 coordinator와 별도 terminal이다. 기본은 coordinator 자신의 provider를 쓰되, task 성격에 맞으면 다른 provider도 선택할 수 있다(launch argv·모델/effort는 해당 provider 문서를 따른다) — 이 경우 그 task의 generator는 coordinator가 아니라 그 provider가 된다.

```bash
# coordinator가 Claude Code인 경우 기본 구현 워커
orca terminal create --worktree active --title sdd-impl-<n> \
  --command "claude --model <resolved-model> --effort <resolved-effort> --permission-mode bypassPermissions" --json
# coordinator가 Codex인 경우
orca terminal create --worktree active --title sdd-impl-<n> \
  --command "codex --model <resolved-model> -c model_reasoning_effort=<resolved-effort> -s workspace-write -a never" --json
orca terminal wait --terminal <impl-handle> --for tui-idle --timeout-ms 60000 --json
```

(구현자는 빌드·테스트 실행이 필요해 Bash 전체 허용 — worktree 격리가 전제. 권한 stall 발견 시 조합을 조정하고 이 스킬에 반영.)

**task 리뷰어(evaluator)** — `orca-review-gate`의 evaluator 선택 규칙(generator 제외, routine=1명 advisory, 고위험=2명 blocking)을 task 단위에 그대로 적용한다. 기준은 **그 task의 generator provider**다(대부분 coordinator 자신이지만, 다른 provider 구현자를 썼다면 그 provider). routine 리뷰어는 가벼운 tier, 고위험 리뷰어는 최고 practical tier에서 고른다. 리뷰어 terminal은 task마다 **재-dispatch로 재사용**하되, 재사용 전 `terminal read`로 launch 모델이 provider 문서 현재 값과 일치하는지 대조한다(불일치 시 새 terminal). 구현자와 같은 provider를 리뷰어로 쓰지 않는다 — generator가 무엇이든 이 원칙은 동일하다.

모든 터미널: `terminal wait --for tui-idle --timeout-ms 60000`(agy는 `--for exit --timeout-ms 960000`) + `terminal read`로 TUI 헤더 모델 확인.

## 3. wave 루프

```bash
orca orchestration task-list --ready --brief --json   # 외부 메모리
orca orchestration dispatch --task <task_id> --to <impl_handle> --inject --json   # 최대 3 병렬
```

- ⚠️ **`check --wait` 단독 대기 금지** (2026-07-20 #211 파일럿 실측): coordinator가 Orca 터미널 내부 세션이면 worker_done이 check 큐가 아니라 **세션 메시지 주입**으로 오거나, `check --wait` 블로킹 중 아예 안 잡힐 수 있다(task 상태는 정상 갱신됨). 기본 대기 = **`task-list --brief --json` 상태 폴링 또는 report 파일 존재 감시**(20-30s 간격), `check --wait`는 보조.
- timeout·`count:0` = 체크포인트. `terminal read` 생사 확인, 활동 중이면 계속 대기.
- decision_gate(워커 ask) → 판단 가능하면 `reply`, 불가하면 사용자 에스컬레이션.
- 구현 `worker_done` → 해당 task의 diff를 **task 리뷰어에 새 task로 재-dispatch**(리뷰 spec: 플랜 task 본문 + 실제 diff + "플랜 대비 검증, 결함은 severity+근거, 코드 수정 금지" + report 경로 `<worktree 루트>/.orca-sdd-review-<task_id>.md`). 고위험 task는 두 번째 evaluator에도 같은 diff를 보내 별도 report를 받는다.
- 리뷰 승인 → 다음 ready task dispatch. 반려 → findings를 구현자에 fix task로 재-dispatch(같은 구현 터미널 재사용).
- worker_done 유실 복구: 산출물(커밋/report)과 task ownership 확인 + `task-update --status completed --result` 수동 복구, 기록. (`orca-review-gate` §4와 동일 절차.)

## 4. 완료

- 전 task + task 리뷰 완료 → **`orca-review-gate` 스킬 호출**(최종 머지 전 게이트 — task 단위 리뷰로는 못 보는 cross-task 통합 이슈를 잡는 별도 층).
- SDD 워커·리뷰어 터미널 close, report 파일 정리. 실행 기록(resolved providers/models/efforts, wave 구성, ask 사례, 복구 발동) 남김.

## 폴백

- orca 런타임 불가: 구현 워커는 기존 `superpowers:subagent-driven-development`로 폴백 가능 — 모델은 provider 문서의 같은 task 유형 등급을 Agent tool `model` 인자로. 폴백 발동은 사용자에게 보고.
- task 리뷰·최종 게이트는 generator-provider 서브에이전트로 대체하지 않는다. provider 문서에서 resolve한 non-generator 모델을 headless로 직접 실행해 동일한 diff/report 계약을 유지한다. 필요한 수의 non-generator evaluator를 확보할 수 없으면 진행을 멈추고 decision gate로 에스컬레이션한다.

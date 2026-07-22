---
name: orca-review-gate
description: Use when running the pre-merge cross-model review gate — the operating procedure. Self-relative — works identically whichever provider (Claude Code, Codex, agy) is the coordinator. Coordinator never edits files directly — fixes are dispatched to a separate generator terminal, keeping the coordinator's context window flat across many review/fix cycles. Cross-model evaluators EXCLUDE the generator's provider (generator ≠ evaluator); routine = 1 advisory evaluator, high-risk = 2 blocking evaluators. Evaluator model/effort per ~/.agents/orca-workflows/models/{claude-code,codex,agy}.md. Replaces the codex plugin companion runtime for review gates.
---

# Orca Cross-Model Review Gate

머지 전 cross-model 리뷰 게이트의 운영 절차. 전송(transport)은 orca orchestration이고, 범용 조작 규율은 `orchestration` 스킬을 따른다.

이 스킬은 **self-relative**하다 — Claude Code·Codex·agy 중 어느 쪽이 coordinator로 이 스킬을 실행하든 같은 텍스트로 동작한다. 아래 규칙 어디에도 특정 provider를 하드코딩하지 않는다 — 세 provider용 사본을 따로 두지 않는 것이 이 스킬의 핵심 설계 목표다.

세 역할을 구분한다:

- **coordinator** — 조율만 한다: diff 확인, terminal 생성·dispatch, 대기, report 종합, 판정. **파일을 직접 편집하지 않는다.**
- **generator** — 코드를 쓰는 쪽(원 구현 또는 fix). 항상 coordinator와 **별도 terminal**이다. 기본 provider는 coordinator 자신의 provider와 같지만(가장 저렴), 다른 provider가 구현했다면(예: `orca-sdd`가 다른 provider 구현 워커를 썼을 때) 그 provider가 generator다.
- **evaluator** — 리뷰만 한다. **generator의 provider를 제외**하고 고른다(self-review 회피).

coordinator가 직접 파일을 편집하면 리뷰·fix 사이클이 반복될수록 coordinator 자신의 컨텍스트가 code-diff로 계속 불어난다. 이를 피하려고 코드 생성은 무조건 별도 generator terminal에서 하고, coordinator 컨텍스트에는 orchestration 메타데이터(task ID·상태·짧은 report)만 남긴다.

## Provider와 evaluator 선택

세 provider: **Anthropic**(claude / Claude Code), **OpenAI**(codex), **Google**(agy / Gemini).

리뷰 시작 전 대상 변경을 티어로 분류한다: **routine** = client-only UI·카피·전사, **고위험** = server·schema·크립토·RLS·auth·migration(경계 의심 시 고위험).

evaluator 선택 규칙 — **generator의 provider는 항상 제외**한다(generator ≠ evaluator, self-review 회피). 대부분의 경우 generator = coordinator 자신의 provider이지만, 다른 provider가 구현한 diff라면 반드시 **그 provider**를 기준으로 아래 규칙을 적용한다(coordinator의 provider가 아니라):

- **routine (1명, advisory)**: generator가 Anthropic이 아니면 **Claude**, generator가 Anthropic이면 **Codex**. (agy는 headless·launch/wait가 느려 routine 단독 evaluator로는 안 쓴다 — 고위험에서만 투입.)
- **고위험 (2명, blocking)**: generator를 제외한 **나머지 두 provider 전부**. 즉 routine에서 고른 evaluator + 나머지 하나(대개 agy, generator가 agy면 Claude+Codex).

이 규칙은 generator가 무엇이든 예외 없이 성립한다:

| generator provider | routine evaluator | 고위험 evaluator |
|---|---|---|
| Claude Code (Anthropic) | Codex | Codex + agy |
| Codex (OpenAI) | Claude | Claude + agy |
| agy (Google) | Claude | Claude + Codex |

⚠️ **자기 provider의 내장 서브에이전트는 evaluator로 금지**한다 — Claude Agent tool 서브에이전트, Codex `spawn_agent` 등은 결국 generator와 같은 provider 모델을 띄우는 것이라 self-review가 된다. 이건 generator가 Claude든 Codex든 agy든 동일하게 적용된다.

## 모델·effort 선택

launch 직전에 아래 문서를 읽고 모델과 effort를 결정한다. 이 스킬에 모델 값을 복제하거나 고정하지 않는다 — provider 모델 세대가 바뀌면 그 문서만 갱신한다.

- `~/.agents/orca-workflows/model-selection.md`
- `~/.agents/orca-workflows/models/claude-code.md`
- `~/.agents/orca-workflows/models/codex.md`
- `~/.agents/orca-workflows/models/agy.md`

routine evaluator는 provider guide의 가벼운 routine tier에서 고르고, 고위험 evaluator들은 각각 최고 practical review tier에서 고른다. 실제 model ID와 effort 값은 provider 문서에서만 읽는다.

## 게이트 운영 절차

**0. 전제** — `orca status --json` ready(실패 시 아래 "폴백"). coordinator는 리뷰 대상 브랜치 체크아웃에서 실행. `orca` CLI를 다수 호출하므로 `bypassPermissions` 또는 `Bash(orca:*)` allowlist로 시작(중간 권한 stall 방지). CLI 기반 coordinator(Codex/agy)는 launch 시 approval·sandbox를 명시한다 — 기본 posture는 `-a never -s workspace-write`이며, 필요한 권한이 이를 넘으면 조용히 완화하지 말고 작업 권한과 대상 경로를 다시 확인한다.

**1. diff 생성**

```bash
git diff "$(git merge-base origin/main HEAD)"...HEAD > <worktree 루트>/.gate-diff.patch
```

merge 대상이 `origin/main`이 아니면 실제 base로 바꾼다. evaluator 전원이 같은 파일을 읽는다. diff는 **workspace 내부**에 둔다(codex sandbox·headless agy가 밖을 못 읽음).

**2. evaluator 준비** (게이트당 1회, re-review에 재사용)

evaluator 선택 표에서 고른 provider만큼 터미널을 만든다. 모델·effort placeholder는 provider 문서에서 현재 값으로 resolve한다.

```bash
# Claude evaluator
orca terminal create --worktree active --title gate-claude \
  --command "claude --model <resolved-claude-model> --effort <resolved-claude-effort>" --json
orca terminal wait --terminal <claude-handle> --for tui-idle --timeout-ms 60000 --json

# Codex evaluator
orca terminal create --worktree active --title gate-codex \
  --command "codex --model <resolved-codex-model> -c model_reasoning_effort=<resolved-codex-effort> -s workspace-write -a never" --json
orca terminal wait --terminal <codex-handle> --for tui-idle --timeout-ms 60000 --json

# agy evaluator (고위험일 때만)
orca terminal create --worktree active --title gate-agy \
  --command "agy -p '<지침 + diff 경로 + report 경로>' --model <resolved-agy-model> --print-timeout 15m" --json
orca terminal wait --terminal <agy-handle> --for exit --timeout-ms 960000 --json
```

- Claude·Codex는 `--for tui-idle`, agy는 headless라 `--for exit`로 기다린다.
- `terminal read`로 실제 launch 시 표기된 모델이 방금 읽은 provider 문서의 선택과 일치하는지 확인한다. 불일치하면 그 terminal을 폐기하고 올바른 launch argv로 다시 만든다(모델은 launch 속성이라 재사용 중 못 바꾼다).
- Codex evaluator는 `-a never`+`workspace-write`라 read-only diff 슬라이싱(`sed`/`grep`)을 승인 없이 실행한다.
- agy는 headless 프로세스라 re-review 때 새 terminal로 다시 실행한다.

**3. dispatch** — task spec 필수 포함: ①diff 절대경로 ②적대적 리뷰 지침(결함·spec-divergence·놓친 리스크; 동의 표명 불필요; **코드 수정 금지**) ③report 절대경로 `<worktree 루트>/.orca-gate-report-<role>.md`(workspace 내부) ④findings = severity(Critical/Important/Minor)+도달 조건+최악 결과+fail-closed 여부 ⑤resolved model·effort 기록 ⑥작성 후 preamble 지시대로 worker_done(payload.reportPath). Claude/Codex는 `task-create` → `dispatch --inject`. agy는 launch prompt에 같은 지침을 넣고 report 파일을 회수한다.

**4. 대기 (rolling)** — `orca orchestration check --wait --types worker_done,escalation,decision_gate --timeout-ms 600000 --json`.
- ⚠️ coordinator가 Orca 터미널 내부 세션이면 worker_done이 check에 안 잡힐 수 있다 → **report 파일 존재 + task 상태 폴링이 기본** 신호, check --wait는 보조. timeout·`count:0`은 체크포인트지 실패가 아니다 — `terminal read`로 생사 확인, 조기 kill 금지.
- decision_gate(evaluator ask) → `orca orchestration reply --id <msg_id> --body "<답>"`.
- **worker_done 유실 복구**: report 존재 + 터미널 idle인데 안 오면 → `orca orchestration task-update --id <task_id> --status completed --result '{"reportPath":"..."}'`. 미해제 dispatch가 재-dispatch를 `already has an active dispatch`로 막으면 이 task-update가 해제한다.

**5. 종합·캘리브레이션** — report dedup → finding별 severity(도달조건·최악결과·fail-closed 여부)로 실 Critical / 극단 edge 분류.
- routine(advisory): coordinator 판단(자신이 dispatch한 코드이므로 finding을 안이하게 각하하지 말 것).
- 고위험(blocking): Critical/Important는 fix 필수. 판정이 불명확하면 `orca orchestration gate-create` + 사용자 에스컬레이션. hot-patch 무한루프 금지.

**6. fix(1회) + re-review** — fix가 필요할 때만, 이 시점에 **generator terminal에 dispatch**한다. coordinator가 직접 편집하지 않는다(orca 일반 규칙과 동일 — 이 게이트도 예외를 두지 않는다). generator terminal이 이미 열려 있으면(예: `orca-sdd`의 구현 워커) 재사용하고, 없으면 여기서 새로 만든다(provider = 원 코드를 작성한 provider, 보통 coordinator 자신):

```bash
orca terminal create --worktree active --title gate-fix \
  --command "<generator provider의 launch 문법 — provider 문서에서 resolve>" --json
orca terminal wait --terminal <fix-handle> --for tui-idle --timeout-ms 60000 --json
orca orchestration task-create --spec "<findings(severity+근거) + 원본 diff 경로 + fix 후 새 diff 생성 지시>" --json
orca orchestration dispatch --task <task_id> --to <fix-handle> --inject --json
```

worker_done 후 새 diff로 재-review: 고위험은 같은 evaluator terminal에 새 task 재-dispatch(재사용 전 launch 모델 대조, agy는 새 terminal) → worker_done → 통과 시 머지. routine은 advisory라 재리뷰 강제 없음.

**7. 종료** — report 회수·삭제, 게이트 터미널 close. 기록: 티어·resolved 모델/effort·evaluator 수·복구/폴백 발동.

## 폴백

- **orca 불가** → transport만 우회: 필요한 evaluator를 orca 없이 **Bash로 직접**(headless) 실행해 diff 리뷰·report 회수(provider 문서 모델 그대로). ⚠️ **Agent tool 서브에이전트 등 generator-provider 서브에이전트는 게이트 evaluator로 금지**(self-review가 됨). 필요한 수의 non-generator evaluator를 확보할 수 없으면 gate를 통과시키지 말고 decision gate로 사용자 에스컬레이션.
- 폴백 발동은 항상 사용자에게 보고한다.

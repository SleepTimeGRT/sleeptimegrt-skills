# Lifecycle Gate Policy — Design (harness-conventions 재정의)

**Date**: 2026-07-22
**Status**: Approved (brainstorming phase) — pending implementation plan

## Context

`harness-conventions` 스킬을 리뷰하던 중 (1) 배포 템플릿(`assets/agents-policy.md`,
`assets/scripts/premerge.sh`, `assets/scripts/premerge.conf.sh`)이 이미 폐기된
`orca-review-gate` 스킬 이름과 "cross-model review"라는, 이번 세션의 orca-workflow
재설계에서 폐기된 근거를 하드코딩하고 있다는 것, (2) 이 스킬이 이름이 암시하는 것보다
`remote-ci-economics`·`token-efficient-gates`와 더 강하게 얽혀 있다는 것을 발견했다.

단순히 이름 교체로 덮지 않고, 이 스킬이 왜 만들어졌는지부터 다시 물어 정체성과 경계를
다시 정의한다.

## 왜 이 스킬이 만들어졌는가 (재정의된 목적)

사용자가 밝힌 4가지 요구사항을 원인-결과로 정리하면:

1. **secret 노출 방지** — gitleaks 같은 도구로 agent의 실수를 기계적으로 막는다. 독립적 요구.
2. **정적 검사(lint/format/typecheck)의 공통화** — 3개 파일럿(medicount, toss-samhaengsi,
   toss-space-goldrush)이 지금까지 각자 다른 임시방편으로 같은 문제를 풀어왔다
   (`references/policy-rationale.md`의 "Superseded arrangements" 참조: medicount는
   husky+stamp, samhaengsi는 pre-merge-local.sh, goldrush는 매 push 풀 verify).
   레포가 독립적으로 관리되다 보니 드리프트가 생기는 게 불편함의 핵심.
3. **githook을 통한 기계적 강제** — 프롬프트/지침은 agent가 빼먹을 수 있지만 git hook은
   무조건 실행된다(determinism). 이건 이 스킬 고유의 판단(훅 배치 결정)이다. 실행된 뒤의
   출력량 압축은 별개로 `token-efficient-gates`의 메커니즘이다.
4. **e2e를 merge gate로 두고 싶지만 remote CI 비용이 부담** — 무거운 검증을 로컬
   premerge로 밀어넣었고, remote CI/branch protection이 없으니 머지를 막을 주체가
   없어져 self-merge + gate-integrity 정책이 필요해졌다.

공통 목표: **secret 노출·정적 오류·e2e 실패가 적절한 개발 생명주기 지점에서 걸러져
기본 브랜치(main)로 전파되지 않게 하는 것**이며, "적절한 지점"은 고정된 정답이 아니라
경험으로 찾아가는 것이므로, 그 답을 레포마다 드리프트 없이 캐노니컬하게 공유하는
메커니즘(템플릿 + hash 기반 drift audit)이 이 스킬의 핵심 가치다.

## 세 스킬의 관계 — 처음부터 다시 설계해도 3분할이 나온다

`remote-ci-economics`(비용 판단, 필요할 때만 도는 감사), `token-efficient-gates`(명령
실행마다 붙는 범용 출력 압축 유틸리티), 그리고 이 스킬(레포에 계속 배포되어 있는
캐노니컬 템플릿 세트)은 트리거 조건과 생명주기가 근본적으로 다르다. 하나로 합치면
description 하나가 세 트리거 패턴을 다 감당해야 해서 스킬 탐색이 나빠지고, 다른 두
스킬이 이 정책을 안 쓰는 레포에서도 독립적으로 쓰이는 재사용성을 잃는다.

**결론: 구조는 유지, 이름·description·Boundaries만 다시 쓴다.** 문제는 구조가 아니라
(a) 이 스킬의 정체성을 설명하는 description이 부실했던 것, (b) 형제 스킬 이름을
근거 인용이 아니라 실행 의존으로 박아넣은 것(정확히 orca-review-gate와 같은 실수),
(c) 실제로 이미 벌어진 asset 소유권 버그(`token-gate.sh` 중복) 였다.

## 결정 사항

### 이름

`harness-conventions` → **`lifecycle-gate-policy`**

이유: "harness"는 범위가 너무 넓어(어떤 개발 도구 scaffold든 지칭 가능) 이 스킬의
실제 정체성(특정 운영 프로필을 위한 opinionated 정책 패키지)을 안 드러낸다. git에만
한정된 내용이 아니므로(개념은 어떤 VCS/워크플로우에도 적용 가능, 구현만 git 기반)
`git-lifecycle-*`가 아니라 `lifecycle-gate-policy`로 확정.

### 범위

**main으로의 머지 시점까지만 책임진다.** 배포(deploy) 시점 게이트는 다루지 않는다 —
머지 이후의 배포 파이프라인은 별도 관심사.

### 새 description (SKILL.md frontmatter)

```
Canonical local development-lifecycle gate policy for solo, agent-driven
repositories with no remote-CI enforcement: pre-commit secret scan + autofix,
static-only pre-push, full premerge verify+e2e, and agent self-merge with
mechanical gate-integrity protection — the local substitute for what remote CI
and branch protection would otherwise enforce. Ships canonical .githooks/ and
premerge/token-gate templates with a hash-based drift audit so N repos share
one answer instead of drifting independently. Use whenever the user asks to
review, compare, unify, audit, standardize, or set up a repository's
development gates, git hooks, verify chains, merge or self-merge policy,
premerge gates, or worktree conventions — and before hand-editing any
.githooks/, token-gate, or premerge file in a repository that follows this
convention, since those files are canonical copies managed here. Stops at
merge into the default branch; does not cover deploy-time gating. Excludes
remote CI cost judgment (remote-ci-economics) and generic agent-facing output
compaction (token-efficient-gates) — cross-references their conclusions but
ships nothing that requires either to be present.
```

### `token-gate.sh` 소유권

**발견한 버그**: `token-efficient-gates/assets/token-gate.sh`와
`harness-conventions/assets/scripts/token-gate.sh`가 이미 2줄(캐노니컬 배너) 차이로
drift 상태다. 게다가 `token-efficient-gates/SKILL.md`는 이 파일을 문서화하지 않는다
(capture.py/audit.py/measure.py만 언급) — 소유권이 불분명한 orphan 사본.

**결정**: `premerge.sh`가 런타임에 이 파일을 직접 `source`하므로, 이 스킬(신규
`lifecycle-gate-policy`)이 캐노니컬 사본을 보유해야 자기완결적이다. 반대로 하면(다른
스킬이 소유, 이 스킬이 가져다 씀) 이번 리뷰의 출발점이었던 "다른 스킬 의존성을 피하고
싶다"는 요구를 그대로 어기게 된다. → `token-efficient-gates/assets/token-gate.sh`는
**삭제**한다. `token-efficient-gates`는 `capture.py`(ad-hoc 실행용)만 자기 메커니즘으로
유지하고, `SKILL.md`의 "Stop at the remote boundary" 절 근처에 한 줄을 추가해
"persistent in-repo adapter가 필요하면 `lifecycle-gate-policy`가 배포하는
`token-gate.sh`를 참조하라"고 문서화한다(코드 의존이 아니라 문서 인용 — 이
스킬은 harness-conventions처럼 별도 "Boundaries" 절 구조를 갖고 있지 않으므로
새 구조를 만들지 않고 기존 절에 문장만 덧붙인다).

### Boundaries 재작성 원칙

형제 스킬(`remote-ci-economics`, `token-efficient-gates`)에 대한 언급은 전부
**근거 인용**으로만 남긴다 — "왜 이 지점에 게이트를 두는지는 `remote-ci-economics`가
분석한다", "출력 압축 메커니즘의 설계 근거는 `token-efficient-gates`가 소유한다" 같은
문장. 배포되는 템플릿(`.githooks/*`, `premerge.sh`, `token-gate.sh`,
`agents-policy.md`)과 `scripts/audit.py`는 두 형제 스킬이 하나도 존재하지 않아도
그대로 동작해야 한다 — 지금도 이미 그렇다(`premerge.sh`는 어느 형제 스킬도 호출하지
않는다). 이 원칙을 SKILL.md Boundaries 절 서두에 명문화한다.

### 정정 대상 — orca-review-gate / cross-model 잔존 참조

grep으로 확인한 9곳, 5개 파일. 배포 템플릿(★)은 3개 파일럿 레포에 이미 적용되어 있다.

| 파일 | 위치 | 현재 | 변경 |
|---|---|---|---|
| `SKILL.md` | 21행 | "cross-model review requirement" | "review requirement" |
| `SKILL.md` | 24행 | "`--review-done` after a clean `orca-review-gate` run" | "`--review-done` after a clean review pass" |
| `SKILL.md` | 87행 (Boundaries) | "**orca-review-gate** executes the cross-model review that `premerge.sh` requires..." | 스킬 이름 삭제, "이 스킬은 리뷰가 언제 필요한지(`--review-done`)만 정의하고 무엇이 그 신호를 채우는지는 무관하다"로 재서술 |
| ★`assets/agents-policy.md` | 10행 | "cross-model review for code changes" | "review for code changes" |
| ★`assets/agents-policy.md` | 22행 | "cross-model review (`orca-review-gate` skill)" | "a clean review pass" |
| ★`assets/scripts/premerge.sh` | 13-14행 (주석) | "run the cross-model review gate first" | "run your review process first" |
| ★`assets/scripts/premerge.sh` | 92행 (섹션 헤더) | `# ---- 3. cross-model review requirement ----` | `# ---- 3. review requirement ----` |
| ★`assets/scripts/premerge.sh` | 97행 (출력 메시지) | "run the cross-model review gate (orca-review-gate), resolve blocking findings" | "resolve blocking findings from your review process" |
| ★`assets/scripts/premerge.conf.sh` | 10행 (주석) | "do not require cross-model review" | "do not require review" |
| `references/policy-rationale.md` | 52행 | "mitigated here by the review being cross-model" | 이번 세션 확정 근거로 교체: fresh-context + skeptical 프롬프트가 편향을 완화하는 레버이고, cross-provider 분리는 필수가 아니라는 판단(`/advisor`가 같은 provider로도 효과 있다는 근거) |
| `references/policy-rationale.md` | 57행 | "Cross-model review is required for code changes only" | "A review pass is required for code changes only" |

## 마이그레이션 계획

1. **이 레포(정본) 수정**: 디렉터리 rename
   `skills/harness-conventions` → `skills/lifecycle-gate-policy`, 위 표의 모든
   교체, description 교체, Boundaries 재작성, `token-gate.sh` orphan 삭제.
2. **파일럿 3개 레포 재적용**: `medicount`, `toss-samhaengsi`, `toss-space-goldrush`의
   `scripts/premerge.sh`, `scripts/premerge.conf.sh`, `AGENTS.md`(harness-conventions
   marker 절)를 새 템플릿으로 재적용. **레포별 독립 커밋**(AGENTS.md 규칙), 재적용 후
   각 레포에서 `audit.py`가 COMPLIANT를 리포트하는지 확인. 이 단계는 오늘 승인과 별개로
   각 레포에 대해 명시적으로 요청받은 뒤 진행한다.
3. 이 스킬은 현재 어떤 agent 풀(`~/.claude/skills`, `~/.codex/skills`,
   `~/.agents/skills`, `~/.gemini/config/skills`)에도 심링크/사본으로 배포되어 있지
   않음을 확인했다 — 3-agent 배포(옛 Task 7)는 이 리네임과 함께 처음 수행해도 되고,
   별도로 미뤄도 된다. 어느 쪽이든 이 설계 문서의 구현 계획(plan) 범위 밖.

## 이번 설계에서 다루지 않는 것

- `~/.agents/skills/orca-review-gate`, `orca-sdd` 심링크가 이미 존재하지 않는
  디렉터리를 가리키는 dangling 상태로 발견됐다(이전 세션에서 orca-workflow 재설계 시
  삭제된 디렉터리, 심링크 정리는 미완료). 이 문서의 스킬 리네임과는 무관한 별도 후속
  정리 대상.
- `orca-evaluate`가 diff 경로를 전달받지 않고 자체 재계산하는 것(이전 세션에서 발견한
  latent bug) — 별도 이슈.

## Open follow-ups

- 파일럿 3개 레포 재적용 시점과 순서는 사용자가 별도로 지정.
- `lifecycle-gate-policy`의 3-agent 심링크 배포 시점은 이 리네임 구현 plan에서
  범위를 확정한다.

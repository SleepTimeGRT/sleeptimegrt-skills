---
name: model-codex
description: Codex(OpenAI) 모델·effort 용도 — coordinator·구현 워커, 그리고 다른 provider가 저자인 코드의 cross-model evaluator
---

# Codex (OpenAI)

**verified_at: 2026-07-21**

`gpt-5.6-*` 계열. coordinator·구현 워커로 쓰거나, 저자 provider가 Codex/OpenAI가 아닐 때 cross-model evaluator로 쓴다(자기 provider가 저자인 리뷰에는 evaluator로 쓰지 않는다 — self-review 회피, 규칙은 `orca-review-gate` 스킬).

launch: `codex --model <id> -c model_reasoning_effort=<low|medium|high|xhigh>` (게이트 리뷰는 `-s workspace-write -a never`로 read-only 슬라이싱 승인 없이, headless는 `codex exec`).

| 모델 | 강점 | 용도 | effort |
|---|---|---|---|
| `gpt-5.6-sol` (Sol) | 최상위 추론 + 장문 recall(MRCR 91.5%, SWE-Bench Pro 64.6%). $5/$30 per 1M | 정확성이 결정적인 리뷰·분석: server 로직·schema/migration·크립토·RLS/auth | xhigh (high=비용 floor) |
| `gpt-5.6-terra` (Terra) | Sol 근접(MRCR 89.6%, SWE-Bench Pro 63.4%), 출력 절반가 $2.50/$15 | 일상 리뷰·분석: client-only UI·카피·전사 수준 변경. 기본 codex 리뷰어 | medium |
| `gpt-5.6-luna` (Luna) | 저가 $1/$6 | ⚠️ 장문 recall 41.3%로 코드 리뷰·장문 작업엔 부적합 | — |

effort는 `-c model_reasoning_effort=<minimal|low|medium|high|xhigh>`로 지정한다. xhigh는 medium 대비 reasoning 토큰 ~8–15배(high는 ~3–5배) — 고위험 게이트는 Claude xhigh 앵커에 맞춰 Sol도 xhigh, 비용이 문제면 high로 내린다.

스모크(2026-07-21, `codex exec`): `gpt-5.6-terra`(medium)·`gpt-5.6-sol`(high·xhigh) 부팅·응답 exit 0. 모델 세대 교체 시 재검증 후 verified_at 갱신.

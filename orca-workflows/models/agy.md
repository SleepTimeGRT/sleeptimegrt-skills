---
name: model-agy
description: agy(Gemini/Google) 모델·effort 용도 — coordinator·구현 워커, 그리고 quota 넉넉한 세 번째 cross-model 시각(evaluator)
---

# agy (Gemini / Google)

**verified_at: 2026-07-21**

Google provider라 Anthropic·OpenAI 어느 쪽과도 겹치지 않는 독립 시각을 준다. quota가 넉넉해 적합한 작업엔 우선 고려한다.

launch: `agy -p '<지침 + diff·report 경로>' --model <token> --print-timeout 15m`. effort는 모델 토큰 suffix(`-high|-medium|-low`) 또는 `--effort`로 지정한다.

| 모델 토큰 | 용도 | effort |
|---|---|---|
| `gemini-3.5-flash-high` | 정확성이 결정적인 리뷰·분석. flash의 effort 천장(위에 xhigh/max 없음) | high |
| `gemini-3.5-flash-medium` | 일상 개발·리뷰 | medium |
| `gemini-3.5-flash-low` | 간단·기계적 작업 | low |

`agy models`에 `gemini-3.6-flash-*`·`gemini-3.1-pro-*`도 있다 — 최신 세대 선호 시 교체를 검토한다. 3.5-flash는 에이전틱 벤치(Terminal-Bench·MCP Atlas 등)에서 3.1-pro를 앞서 현행 기본. 단 SWE-Bench Pro 55.1%로 Opus/Sol 앵커보다 낮아, 고위험에선 codex Sol 뒤의 **독립 시각(secondary)** 역할이다.

스모크(2026-07-21, `agy -p`): `gemini-3.5-flash-high` 부팅·응답 exit 0. 모델 세대 교체 시 재검증 후 verified_at 갱신.

quota·오류로 호출이 skip될 수 있다 — 그때의 대체 처리는 `orca-review-gate` 스킬이 소유한다.

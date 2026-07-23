---
name: model-agy
description: agy(Gemini/Google) 모델·effort 용도 — coordinator·구현 워커·evaluator 어디에나 쓸 수 있음, quota가 넉넉해 적합한 작업엔 우선 고려
---

# agy (Gemini / Google)

**verified_at: 2026-07-21**

quota가 넉넉해 coordinator·구현 워커·evaluator 어디에든 적합한 작업엔 우선 고려한다.

launch: `agy -p '<지침 + diff·report 경로>' --model <token> --print-timeout 15m`. effort는 모델 토큰 suffix(`-high|-medium|-low`) 또는 `--effort`로 지정한다.

| 모델 토큰 | 용도 | effort |
|---|---|---|
| `gemini-3.5-flash-high` | 정확성이 결정적인 리뷰·분석. flash의 effort 천장(위에 xhigh/max 없음) | high |
| `gemini-3.5-flash-medium` | 일상 개발·리뷰 | medium |
| `gemini-3.5-flash-low` | 간단·기계적 작업 | low |

`agy models`에 `gemini-3.6-flash-*`·`gemini-3.1-pro-*`도 있다 — 최신 세대 선호 시 교체를 검토한다. 3.5-flash는 에이전틱 벤치(Terminal-Bench·MCP Atlas 등)에서 3.1-pro를 앞서 현행 기본. 단 SWE-Bench Pro 55.1%로 Opus/Sol 앵커보다 낮아, 고위험 판단에는 상대적으로 약하다.

`gemini-3.6-flash`(2026-07-21 릴리스)는 OSWorld-Verified 컴퓨터 사용 78.4%→83%, GDM-MRCR v2 128k 롱컨텍스트 77.3%→91.8%로 두 영역에서 3.5-flash 대비 뚜렷한 개선이 외부에서 확인된다(웹 검색 기준, 이 리포에서 직접 검증한 값은 아님). **아직 `agy -p` 스모크 테스트를 거치지 않았다** — 컴퓨터 사용/롱컨텍스트 스켑티컬 재확인 tier(`~/.agents/orca-workflows/model-selection.md`)에 기본값으로 승격하기 전에 아래 3.5-flash와 같은 방식으로 부팅·응답 exit 0 확인 후 verified_at을 갱신할 것.

**agent e2e(Playwright)**: agy/Antigravity CLI에 BrowserMCP를 설정하면 accessibility-tree 기반 Playwright 브라우저 조작이 가능하다(`~/.gemini/settings.json` 또는 Antigravity CLI 설정에 MCP 서버 등록). 스크린샷·좌표 클릭보다 UI 변경에 덜 깨지므로 `orca-evaluate`의 agent-e2e 스트림은 이 조합(agy + BrowserMCP)을 기본으로 한다 — 실제 launch 전 이 리포에서 BrowserMCP 연결 자체를 한 번 스모크 테스트할 것.

스모크(2026-07-21, `agy -p`): `gemini-3.5-flash-high` 부팅·응답 exit 0. 모델 세대 교체 시 재검증 후 verified_at 갱신.

quota·오류로 호출이 skip될 수 있다 — 그때의 대체 처리는 `orca-evaluate`/`orca-task-runner` 스킬의 폴백 절이 소유한다.

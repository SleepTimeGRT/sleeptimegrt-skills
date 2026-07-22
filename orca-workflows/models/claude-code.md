---
name: model-claude-code
description: Claude Code(Anthropic) 모델·effort 용도 — coordinator·SDD 구현 워커·task 리뷰
---

# Claude Code (Anthropic)

**verified_at: 2026-07-21**

coordinator 세션과 SDD 구현 워커에 쓰는 provider.

launch: `claude --model <id> --effort <low|medium|high|xhigh|max>`. SDD 구현 워커는 `--permission-mode bypassPermissions`(빌드·테스트 실행에 Bash 전체 필요, worktree 격리 전제).

| 모델 | 강점 | 용도 | effort |
|---|---|---|---|
| `claude-opus-4-8` | 최상위 판단 | coordinator, high-risk 직접 작업, Claude Code `/advisor` 리뷰 백엔드 | xhigh (coordinator는 세션값) |
| `claude-fable-5` | 강한 설계력 | 아키텍처·설계 비중 큰 구현 | high (보안·high-risk는 xhigh) |
| `claude-sonnet-5` | 균형 | 통합·판단 구현 | high |
| `claude-haiku-4-5-20251001` | 빠르고 저렴 | 전사·기계적 구현 | — (effort 미지원) |

- **Sonnet 5 패턴(routine 기본)**: Sonnet 5 @ high로 작업하고, 더 깊은 리뷰가 필요하면 generator effort를 올리는 대신 **Claude Code의 `/advisor` 기능**(상위 리뷰 모델 = Opus 4.8 @ xhigh 백엔드)으로 리뷰받는다. `/advisor`는 **Sonnet 5로 작업할 때** 쓴다.
- **Fable 5**: high로 작업하고, 보안·민감(high-risk) 작업은 **자체 effort를 xhigh로** 올린다. fable엔 `/advisor`(opus)를 붙이지 않는다.
- Opus를 primary generator로 직접 쓰는 건 task가 high-risk일 때뿐.
- Haiku 4.5는 Anthropic effort 파라미터 지원 모델 목록에 없다 → haiku 워커는 `--effort`를 **생략**한다. `--effort`는 나머지 3개 모델에만 준다.
- effort 지원: xhigh/max는 Fable 5·Opus 4.8·Sonnet 5, high는 Haiku 제외 전 모델. Opus 4.8은 문서상 코딩·에이전틱에 xhigh 시작을 명시 권장(max는 프런티어 문제 전용 — 과추론·비용 위험).
- **Opus 4.8 @ xhigh는 다른 provider effort의 앵커**다(SWE-Bench Pro 리드) — 캘리브레이션은 model-selection.md 참조.

⚠️ 저자가 Anthropic이면 Claude는 cross-model 리뷰 게이트의 evaluator에서 제외한다(self-review 회피) — 게이트 절차는 `orca-review-gate` 스킬.

# Orca Generator/Evaluator Gate Rewiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move e2e/pgTAP execution from `orca-evaluate` into a new task-level gate inside `orca-task-runner` (before handoff), reorder `orca-evaluate` so agent-e2e runs before code review and feeds it, and add a `GATE_FAIL` routing path in `orca-workflow` for when that new gate can't be passed.

**Architecture:** Three existing SKILL.md files get edited in place — no new files, no scripts, no code. Each is a procedural markdown document consumed by an agent session; "correctness" here means the prose is unambiguous, internally consistent (section numbers referenced from within the same file or from other files actually exist and match), and doesn't silently drop an existing rule. There is no compiler or test runner for these files, so each task's "test" is a set of `grep`/`sed` checks run before and after the edit — written first so they demonstrably fail on the current content, then pass once the edit lands.

**Tech Stack:** Markdown (Claude Code / Codex / agy Agent Skills format), bash for verification.

## Global Constraints

- Keep `SKILL.md` concise and procedural (`AGENTS.md`: "Keep `SKILL.md` concise and procedural. Put trigger conditions in its YAML `description`.").
- Prefer editing existing files; do not create README/changelog files inside skill folders (`AGENTS.md`).
- Preserve existing exit-code/routing semantics when refactoring gate output (`AGENTS.md` "Gate-output design constraints" — PASS/WARN/FAIL/SKIP-equivalent outcomes must stay distinct; here the equivalent is PASS/FAIL/ESCALATE/GATE_FAIL staying distinct and none silently merged).
- Only commit when explicitly proceeding through this plan — the user approved running it via `writing-plans` → execution, which is the explicit request `AGENTS.md` requires for commits in this repo. Do not push.
- Every section-number cross-reference (`§N`), whether inside the same file or from another file in this repo, must point at a section that actually exists with that number after all edits land. Task 4 exists specifically because one such cross-reference (in `orca-workflows/model-selection.md`) goes stale from Task 3's renumbering and the original design spec incorrectly assumed that file needed no changes — verified by grep, not assumed.

---

### Task 1: `orca-task-runner` — add the Task-레벨 게이트 section

**Files:**
- Modify: `skills/orca-task-runner/SKILL.md` (insert new section after current §5 "Wave 루프", renumber current §6 "완료" to §7)

**Interfaces:**
- Consumes: nothing new — reads the task's own merged worktree diff (all subtasks already committed there per existing §2's "병렬 커밋 안전 규칙").
- Produces: the value **`GATE_FAIL`** as a possible return from this skill to `orca-workflow`, alongside the existing "task 전체 diff 경로" return. Task 2 (`orca-workflow`) consumes this exact string `GATE_FAIL` to route to Inspecting without calling `orca-evaluate`.

- [ ] **Step 1: Write the failing verification check**

Run:
```bash
grep -c "Task 레벨 게이트" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
grep -c "GATE_FAIL" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
grep -oE "^## [0-9]+\." /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
```
Expected: first two commands print `0` (section and marker don't exist yet); third prints `## 0.` through `## 6.` (current: 전제/Contract 제안/Subtask DAG 구성/Wave 준비/Subtask 게이트/Wave 루프/완료 — i.e. 0,1,2,3,4,5,6).

- [ ] **Step 2: Insert the new section**

In `skills/orca-task-runner/SKILL.md`, replace:

```markdown
## 6. 완료

전 subtask 완료 → task 전체 diff를 정리해 `orca-workflow`에 반환한다(diff 경로 + resolved providers/models + wave 구성 기록). **`orca-evaluate`는 이 스킬이 직접 호출하지 않는다** — `orca-workflow`가 호출한다.
```

with:

```markdown
## 6. Task 레벨 게이트

subtask 전부가 끝나 합쳐진 task 전체 diff 기준으로, 딱 한 번 재검증한다. subtask 게이트(§4)는 같은 wave 안에서 병렬 실행되는 형제 subtask의 커밋을 놓칠 수 있어(race) — 어떤 subtask가 자기 게이트를 실행하는 시점에 같은 wave의 형제가 아직 커밋 전일 수 있다 — 그 어떤 subtask의 통과도 "task 전체가 합쳐진 뒤"를 보장하지 않는다. 이 게이트가 그 구멍을 메운다.

- typecheck / unit test / formatter / linter를 task 전체 diff 기준으로 재실행.
- e2e·pgTAP 실행(결정론적, 모델 개입 없음):

```bash
bash -lc '<repo의 e2e 커맨드> > <worktree 루트>/.gate-e2e.log 2>&1; \
  echo EXIT:$? > <worktree 루트>/.gate-e2e-summary.txt'
bash -lc '<repo의 pgTAP 커맨드, 예: pg_prove> > <worktree 루트>/.gate-pgtap.log 2>&1; \
  echo EXIT:$? > <worktree 루트>/.gate-pgtap-summary.txt; \
  grep -c "not ok" <worktree 루트>/.gate-pgtap.log >> <worktree 루트>/.gate-pgtap-summary.txt'
```

실패 시 subtask 게이트(§4)와 같은 방식으로 스스로 고치고 재시도한다. 단 subtask 게이트와 달리 **재시도 한도 2회**(무한 자가치유가 아니다 — `orca-workflow` §2d의 evaluate-FAIL 재시도 한도와 같은 숫자로 맞췄다). 2회 시도 후에도 통과 못하면 `orca-evaluate`를 호출하지 않고 `orca-workflow`에 **`GATE_FAIL`**을 직접 반환한다 — 기계적으로도 안 돌아가는 코드를 agent e2e·code review 같은 비싼 단계에 태울 이유가 없다.

## 7. 완료

Task 레벨 게이트(§6)를 통과하면 → task 전체 diff를 정리해 `orca-workflow`에 반환한다(diff 경로 + resolved providers/models + wave 구성 기록). **`orca-evaluate`는 이 스킬이 직접 호출하지 않는다** — `orca-workflow`가 호출한다. (§6에서 `GATE_FAIL`을 반환한 경우엔 diff를 넘기지 않는다 — 그 자체가 반환값이다.)
```

- [ ] **Step 3: Run verification again to confirm it passes**

Run:
```bash
grep -c "Task 레벨 게이트" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
grep -c "GATE_FAIL" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
grep -oE "^## [0-9]+\." /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
```
Expected: first prints `1`, second prints `2` (once in §6 body, once in the §7 parenthetical), third prints `## 0.` through `## 7.` with no gaps or repeats.

- [ ] **Step 4: Commit**

```bash
cd /Users/minchul/Projects/sleeptimegrt-skills
git add skills/orca-task-runner/SKILL.md
git commit -m "$(cat <<'EOF'
feat: add task-level gate to orca-task-runner for e2e/pgTAP before handoff

Subtask gates only see a partial, racy snapshot of the shared worktree
(siblings in the same wave can commit after this subtask already ran
its own gate), so no single subtask's typecheck/lint/test run actually
covers the merged task. Add a task-level re-run of those cheap checks
plus e2e/pgTAP once all subtasks are done, capped at 2 self-heal
retries, returning GATE_FAIL to orca-workflow (skipping orca-evaluate
entirely) if the cap is hit — no point spending an expensive evaluate
pass on a diff that doesn't mechanically work yet.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `orca-workflow` — route `GATE_FAIL` straight to Inspecting

**Files:**
- Modify: `skills/orca-workflow/SKILL.md` (§2b/§2d, §3 Inspecting)

**Interfaces:**
- Consumes: the `GATE_FAIL` string produced by Task 1's `orca-task-runner` change.
- Produces: nothing new for later tasks — this is a leaf routing change.

- [ ] **Step 1: Write the failing verification check**

Run:
```bash
grep -c "GATE_FAIL" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-workflow/SKILL.md
```
Expected: `0`.

- [ ] **Step 2: Edit §2b/§2d**

In `skills/orca-workflow/SKILL.md`, replace:

```markdown
**2b. Generate** — `orca-task-runner` 호출, task 전체 diff 경로를 결과로 받는다.

**2c. Evaluate** — `orca-evaluate` 호출(diff 경로 전달), PASS / FAIL / ESCALATE 중 하나를 결과로 받는다.

**2d. 라우팅**:
- PASS → merge 진행(squash), task 종료.
- FAIL → 재시도 카운터 확인. **2회 미만이면** feedback과 함께 `orca-task-runner`에 재-dispatch(2b로). **2회 도달하면** inspecting으로.
- ESCALATE → 재시도 카운트 무관하게 즉시 inspecting.
```

with:

```markdown
**2b. Generate** — `orca-task-runner` 호출, 결과로 **task 전체 diff 경로** 또는 **`GATE_FAIL`**을 받는다(`orca-task-runner`가 자기 task-레벨 게이트를 재시도 한도(2회) 안에 못 넘긴 경우 — `skills/orca-task-runner/SKILL.md` §6).

**2b-1. GATE_FAIL 라우팅** — `orca-evaluate`를 호출하지 않고 바로 **3. Inspecting**으로 간다. `orca-task-runner`가 이미 자기 재시도 예산을 다 썼으므로 여기서 추가 재시도를 걸지 않는다(이중 카운팅 방지). Inspecting 보고에 "evaluate 호출 안 됨(GATE_FAIL) — 기계적 게이트 실패"를 명시해 아래 FAIL/ESCALATE와 구분한다.

**2c. Evaluate** — (§2b가 diff 경로를 반환했을 때만) `orca-evaluate` 호출(diff 경로 전달), PASS / FAIL / ESCALATE 중 하나를 결과로 받는다.

**2d. 라우팅**:
- PASS → merge 진행(squash), task 종료.
- FAIL → 재시도 카운터 확인. **2회 미만이면** feedback과 함께 `orca-task-runner`에 재-dispatch(2b로). **2회 도달하면** inspecting으로.
- ESCALATE → 재시도 카운트 무관하게 즉시 inspecting.
```

- [ ] **Step 3: Edit §3 Inspecting to mention GATE_FAIL**

Replace:

```markdown
사람 체크포인트. 보고 내용: issue 번호, PASS/FAIL/ESCALATE 판정 근거, 재시도 횟수, resolved providers/models. 사람이 고를 수 있는 것: 계속(피드백 반영해 재시도) / 재계획(요구사항 자체를 다시 논의 — 1a 또는 issue 수정으로 복귀) / 중단.
```

with:

```markdown
사람 체크포인트. 보고 내용: issue 번호, PASS/FAIL/ESCALATE/GATE_FAIL 중 어느 것으로 왔는지와 그 근거, 재시도 횟수, resolved providers/models. GATE_FAIL은 `orca-evaluate`가 아예 호출되지 않았다는 뜻이므로 그 사실을 반드시 표시한다. 사람이 고를 수 있는 것: 계속(피드백 반영해 재시도) / 재계획(요구사항 자체를 다시 논의 — 1a 또는 issue 수정으로 복귀) / 중단.
```

- [ ] **Step 4: Run verification again to confirm it passes**

Run:
```bash
grep -o "GATE_FAIL" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-workflow/SKILL.md | wc -l
```
Expected: `5` (2b body, 2b-1 heading, 2b-1 body, Inspecting body ×2 — `grep -c` undercounts because two of these occurrences share a line with another; use `grep -o | wc -l` to count every occurrence regardless of line).

- [ ] **Step 5: Commit**

```bash
cd /Users/minchul/Projects/sleeptimegrt-skills
git add skills/orca-workflow/SKILL.md
git commit -m "$(cat <<'EOF'
feat: route GATE_FAIL from orca-task-runner straight to Inspecting

orca-task-runner can now fail its own task-level gate after exhausting
its retry budget and return GATE_FAIL instead of a diff. Skip
orca-evaluate entirely in that case (nothing to evaluate yet) and go
straight to the human checkpoint — orca-workflow doesn't add its own
retry on top, since task-runner already spent its budget internally.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `orca-evaluate` — drop e2e/pgTAP, run agent-e2e before code review

**Files:**
- Modify: `skills/orca-evaluate/SKILL.md` (frontmatter description, §0, intro paragraph, §1, renumber §2↔§3, §4, 폴백)

**Interfaces:**
- Consumes: nothing new from Task 1/2 directly (it now simply never receives e2e/pgTAP data — that's an omission, not a new interface).
- Produces: the new section numbering (§1 Contract, §2 Test gate/agent-e2e, §3 Diff 리뷰/code review, §4 리포트 합성) that Task 4 must match when it fixes the stale cross-reference in `model-selection.md`.

- [ ] **Step 1: Write the failing verification check**

Run:
```bash
grep -c "pg_prove" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
grep -oE "^## [0-9]+\." /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
```
Expected: first prints `1` (the pgTAP execution command, `pg_prove`, is still here — this is the actual thing being removed; plain mentions of the word "pgTAP" will remain afterward as explanatory notes, so don't grep for that word as the pass/fail signal); second prints `## 0.` through `## 4.` with the current order (0=launch, 1=Contract, 2=Diff 리뷰, 3=통합 테스트 스트림, 4=리포트 합성) — i.e. code review is currently §2 and the test streams are §3, the reverse of the target order.

- [ ] **Step 2: Update the frontmatter description**

Replace:

```yaml
description: Use when evaluating a completed task's diff before merge — this session itself runs on agy(Gemini) for its speed/cost/computer-use strength (running e2e/agent-e2e/pgTAP streams and synthesizing everything into one report), while it spawns a separate strong-coding-agent terminal for the two judgment calls it can't make well itself — sprint contract approval and diff code review — against the issue's Acceptance criteria. Returns PASS, FAIL-with-feedback, or ESCALATE. Self-relative.
```

with:

```yaml
description: Use when evaluating a completed task's diff before merge — this session itself runs on agy(Gemini) for its speed/cost/computer-use strength (running the agent-e2e test gate and synthesizing everything into one report; e2e/pgTAP already passed a task-level gate in orca-task-runner before this diff arrived, so this skill never touches them), while it spawns a separate strong-coding-agent terminal for the two judgment calls it can't make well itself — sprint contract approval and diff code review informed by the agent-e2e result — against the issue's Acceptance criteria. Returns PASS, FAIL-with-feedback, or ESCALATE. Self-relative.
```

- [ ] **Step 3: Update §0's stream/section references**

Replace:

```markdown
**이 세션은 기본적으로 agy(Gemini)로 뜬다** — §3의 통합 테스트 스트림 실행(특히 agent e2e)과 §4의 리포트 합성이 이 세션의 핵심 업무이고, Gemini의 속도·비용·컴퓨터 사용 강점이 정확히 여기에 맞기 때문이다(`~/.agents/orca-workflows/model-selection.md`의 Computer Use / Long-Context 축, `~/.agents/orca-workflows/models/agy.md` 참고). `gemini-3.6-flash`는 아직 이 리포에서 스모크 테스트 전이므로, 검증 전엔 `gemini-3.5-flash-high`로 launch한다.

**단, §1(Contract 검토)과 §2(Diff 리뷰)의 실제 판단은 이 세션의 몫이 아니다.** 둘 다 "코드/구현이 기술적으로 타당한가"를 보는 일이고, Gemini는 `model-selection.md`의 High Risk tier(production review/final approval)에서 SWE-Bench Pro 기준 Opus/Sol 앵커보다 낮다고 리포 스스로 표시해둔 지점이다 — 그래서 이 세션(evaluator)은 두 판단 모두 **강한 coding 모델 세션을 스폰**해서 맡기고, 자신은 relay + 최종 리포트 합성만 한다.
```

with:

```markdown
**이 세션은 기본적으로 agy(Gemini)로 뜬다** — §2의 agent e2e 실행과 §4의 리포트 합성이 이 세션의 핵심 업무이고, Gemini의 속도·비용·컴퓨터 사용 강점이 정확히 여기에 맞기 때문이다(`~/.agents/orca-workflows/model-selection.md`의 Computer Use / Long-Context 축, `~/.agents/orca-workflows/models/agy.md` 참고). e2e·pgTAP은 이 세션에 들어오지 않는다 — `orca-task-runner`의 task-레벨 게이트(`skills/orca-task-runner/SKILL.md` §6)를 이미 통과한 뒤에만 이 스킬이 호출되기 때문에 전량 신뢰하고 재검증하지 않는다. `gemini-3.6-flash`는 아직 이 리포에서 스모크 테스트 전이므로, 검증 전엔 `gemini-3.5-flash-high`로 launch한다.

**단, §1(Contract 검토)과 §3(Diff 리뷰)의 실제 판단은 이 세션의 몫이 아니다.** 둘 다 "코드/구현이 기술적으로 타당한가"를 보는 일이고, Gemini는 `model-selection.md`의 High Risk tier(production review/final approval)에서 SWE-Bench Pro 기준 Opus/Sol 앵커보다 낮다고 리포 스스로 표시해둔 지점이다 — 그래서 이 세션(evaluator)은 두 판단 모두 **강한 coding 모델 세션을 스폰**해서 맡기고, 자신은 relay + 최종 리포트 합성만 한다.
```

- [ ] **Step 4: Update §1's internal reference and swap §2/§3 content**

In §1 (Contract 검토), replace:

```markdown
`orca-task-runner`가 구현 전 제안서(범위 + 검증 방법)를 보내오면, 이 세션(evaluator)이 직접 판단하지 않고 **coding agent 터미널을 스폰**해서 issue의 원본 `## Acceptance criteria`에 대조 검토를 맡긴다 — 제안된 파일 범위·검증 방법이 실제 코드베이스에서 기술적으로 타당한지 보는 일이라 §2 code-reviewer와 같은 이유로 강한 reasoning 모델이 낫다.
```

with:

```markdown
`orca-task-runner`가 구현 전 제안서(범위 + 검증 방법)를 보내오면, 이 세션(evaluator)이 직접 판단하지 않고 **coding agent 터미널을 스폰**해서 issue의 원본 `## Acceptance criteria`에 대조 검토를 맡긴다 — 제안된 파일 범위·검증 방법이 실제 코드베이스에서 기술적으로 타당한지 보는 일이라 §3 code-reviewer와 같은 이유로 강한 reasoning 모델이 낫다.
```

And later in §1, replace:

```markdown
두 번의 coding agent 스폰(여기 §1과 아래 §2)은 시간상 멀리 떨어져 있다(§1은 구현 시작 전, §2는 전체 subtask wave가 끝난 뒤) — 하나의 터미널을 그 사이 계속 띄워두지 않고, 그때그때 fresh-context로 새로 스폰한다.
```

with:

```markdown
두 번의 coding agent 스폰(여기 §1과 아래 §3)은 시간상 멀리 떨어져 있다(§1은 구현 시작 전, §3은 전체 subtask wave가 끝난 뒤) — 하나의 터미널을 그 사이 계속 띄워두지 않고, 그때그때 fresh-context로 새로 스폰한다.
```

Now replace the entire current §2 + §3 block:

```markdown
## 2. Diff 리뷰 (coding agent 스폰)

```bash
git diff "$(git merge-base origin/main HEAD)"...HEAD > <worktree 루트>/.evaluate-diff.patch
```

fresh-context code-reviewer terminal을 하나 스폰한다(이 evaluator 세션·generator와 별도 세션 — **강한 reasoning 모델 고정**, `model-selection.md` High Risk tier 참고: Claude Opus 4.8 xhigh / Codex Sol xhigh 등. "provider 자유, 가장 싼 provider"가 아니다 — 코드 정오 판단은 이 세션의 Gemini가 약하다고 표시된 지점이라 일부러 다른 모델을 쓰는 것). 리뷰어는 반드시 이 두 가지를 갖는다: ①skeptical 지침("동의 표명 불필요, 결함·spec-divergence만 보고, 근거 있는 우려를 안이하게 넘기지 말 것") ②issue의 acceptance criteria 원문.

```bash
orca terminal create --worktree active --title eval-review \
  --command "<강한 reasoning provider의 launch 문법 — provider 문서에서 resolve>" --json
orca terminal wait --terminal <review-handle> --for tui-idle --timeout-ms 60000 --json
orca orchestration task-create --spec "<diff 절대경로 + acceptance criteria 원문 + skeptical 리뷰 지침 + report 경로 + 코드 수정 금지>" --json
orca orchestration dispatch --task <task_id> --to <review-handle> --inject --json
```

report는 severity(Critical/Important/Minor) + 도달 조건 + 최악 결과 + fail-closed 여부를 포함해야 한다. 이 report는 작아서(요약된 finding 목록) 이 evaluator 세션이 직접 읽는다.

## 3. 통합 테스트 스트림

코드 리뷰와 별개로, 실제 실행이 필요한 검증을 스트림별로 돌린다 — 이건 이 세션(Gemini)의 핵심 업무다.

- **e2e** — 브라우저 조작 없는 API/서비스 레벨 통합 테스트. 순수 bash 터미널(모델 없음). 테스트 러너에 구조화된 리포터(JSON/JUnit 등)가 있으면 그걸로 pass/fail 요약을 뽑고, 없으면 exit code + 로그 경로만 반환한다.
- **agent e2e** — 앱을 직접 조작하는 e2e. Playwright MCP(accessibility-tree 기반이라 스크린샷·좌표 클릭보다 UI 변경에 덜 깨진다)를 붙인 agy(Gemini) 세션을 별도 터미널로 스폰한다 — 이 세션 자체가 이미 에이전트이므로, worker_done에 자기가 무엇을 했고 무엇이 실패했는지 자연어 요약을 실어 보낸다.
- **pgTAP** — DB 레벨 assertion 테스트. TAP 포맷(`ok`/`not ok`) 자체가 이미 기계 판독 가능한 구조이므로, **실행하는 그 bash 터미널이** `pg_prove` exit code + `not ok` 라인 grep으로 pass/fail 카운트와 실패 테스트 이름을 뽑아 작은 요약 파일에 쓴다. 모델은 전혀 개입하지 않는다.

```bash
# e2e / pgTAP — 순수 bash, 모델 없음
orca terminal create --worktree active --title eval-<stream> \
  --command "bash -lc '<e2e | pgTAP 커맨드> > <worktree 루트>/.evaluate-<stream>.log 2>&1; \
    echo EXIT:$? > <worktree 루트>/.evaluate-<stream>-summary.txt; \
    grep -c \"not ok\" <worktree 루트>/.evaluate-<stream>.log >> <worktree 루트>/.evaluate-<stream>-summary.txt'" --json
orca terminal wait --terminal <stream-handle> --for exit --timeout-ms 1800000 --json
```

이 세션(evaluator)은 각 스트림의 자기 요약을 **그대로 믿지 않는다** — 이미 이 세션 자체가 롱컨텍스트 Gemini이므로, 3개 스트림의 원본 로그를 직접(별도 터미널 스폰 없이) 읽어서 pass/fail 카운트가 실제로 맞는지, 특히 agent e2e가 "성공했다"고 자체 보고했더라도 트레이스 상에서 조용히 막히거나 우회한 흔적은 없는지 확인한다. 이 재확인에 별도 터미널을 또 스폰할 필요가 없다 — 그게 필요했던 건 evaluator 세션 자체가 롱컨텍스트 모델이 아니었을 때 얘기다.
```

with:

```markdown
## 2. Test Gate: Agent e2e (evaluator 자신이 실행)

앱을 직접 조작하는 e2e. Playwright MCP(accessibility-tree 기반이라 스크린샷·좌표 클릭보다 UI 변경에 덜 깨진다)를 붙인 agy(Gemini) 세션을 별도 터미널로 스폰한다 — 이 세션 자체가 이미 에이전트이므로, worker_done에 자기가 무엇을 했고 무엇이 실패했는지 자연어 요약을 실어 보낸다. (e2e·pgTAP은 더 이상 여기서 돌지 않는다 — `orca-task-runner`의 task-레벨 게이트로 이관되어 이 스킬에 들어오는 diff는 이미 그 둘을 통과한 상태다. evaluator는 그 사실을 전량 신뢰하고 재검증하지 않는다.)

```bash
orca terminal create --worktree active --title eval-agent-e2e \
  --command "agy -p '<Playwright MCP 지침 + 테스트 시나리오>' --model <token> --print-timeout 15m" --json
orca orchestration task-create --spec "<앱 URL/worktree 경로 + 테스트 시나리오 + 실패 시 무엇을 관찰했는지 요약해서 worker_done에 실어달라는 지침>" --json
orca orchestration dispatch --task <task_id> --to <agent-e2e-handle> --inject --json
```

이 세션(evaluator)은 그 자기 요약을 **그대로 믿지 않는다** — 이미 이 세션 자체가 롱컨텍스트 Gemini이므로, 원본 트레이스를 직접(별도 터미널 스폰 없이) 읽어서 "성공했다"는 보고가 실제로 맞는지, 조용히 막히거나 우회한 흔적은 없는지 확인한다.

## 3. Diff 리뷰 (coding agent 스폰, agent e2e 결과 반영)

```bash
git diff "$(git merge-base origin/main HEAD)"...HEAD > <worktree 루트>/.evaluate-diff.patch
```

fresh-context code-reviewer terminal을 하나 스폰한다(이 evaluator 세션·generator와 별도 세션 — **강한 reasoning 모델 고정**, `model-selection.md` High Risk tier 참고: Claude Opus 4.8 xhigh / Codex Sol xhigh 등. "provider 자유, 가장 싼 provider"가 아니다 — 코드 정오 판단은 이 세션의 Gemini가 약하다고 표시된 지점이라 일부러 다른 모델을 쓰는 것). 리뷰어는 반드시 이 세 가지를 갖는다: ①skeptical 지침("동의 표명 불필요, 결함·spec-divergence만 보고, 근거 있는 우려를 안이하게 넘기지 말 것") ②issue의 acceptance criteria 원문 ③**§2 agent e2e 결과 요약** — diff만으로는 안 보이는 런타임 동작(무엇이 실제로 실패했는지)을 code review가 근거로 쓸 수 있게 한다.

```bash
orca terminal create --worktree active --title eval-review \
  --command "<강한 reasoning provider의 launch 문법 — provider 문서에서 resolve>" --json
orca terminal wait --terminal <review-handle> --for tui-idle --timeout-ms 60000 --json
orca orchestration task-create --spec "<diff 절대경로 + acceptance criteria 원문 + §2 agent e2e 결과 요약 + skeptical 리뷰 지침 + report 경로 + 코드 수정 금지>" --json
orca orchestration dispatch --task <task_id> --to <review-handle> --inject --json
```

report는 severity(Critical/Important/Minor) + 도달 조건 + 최악 결과 + fail-closed 여부를 포함해야 한다. 이 report는 작아서(요약된 finding 목록) 이 evaluator 세션이 직접 읽는다.

**agent e2e(§2)와 code review(§3)는 순차 실행이다** — code review가 agent e2e 결과를 입력으로 받아야 하므로 병렬로 못 돌린다. wall-clock이 늘어나는 트레이드오프를 감수한 것이다.
```

- [ ] **Step 5: Update §4 리포트 합성**

Replace:

```markdown
## 4. 리포트 합성 (evaluator 역할)

§1(contract 판정 기록) + §2(code-reviewer report) + §3(통합 테스트 스트림 결과, 원본 로그 직접 확인 포함) 세 가지를 이 세션이 하나의 리포트로 합성한다 — 이건 판단이 아니라 이미 나온 판단들을 압축하는 일이라(어려운 판단은 §1·§2에서 강한 reasoning 모델이 이미 끝냄) Gemini가 해도 된다. PASS/FAIL/ESCALATE 매핑도 아래 고정 규칙을 그대로 적용하는 것이라 이 세션이 직접 낸다:

- **PASS** — code-reviewer report에 Critical/Important finding 없음, contract 판정 승인 상태 유지, repo에 적용되는 통합 테스트 스트림(e2e·agent e2e·pgTAP 중 해당하는 것) 전부 통과(자기 요약과 재확인 결과가 일치).
- **FAIL** — 구체적 finding(severity+근거) + 수정 방향을 `orca-workflow`에 반환한다. (재시도는 `orca-workflow`가 관리한다 — 이 스킬은 재-dispatch하지 않는다. `orca-workflow`가 이 리포트를 받아 재시도 카운터를 세고, 필요하면 `orca-task-runner`에 재-dispatch — evaluator가 task-runner를 직접 부르지 않는다.)
- **ESCALATE** — 다음 중 하나면 재시도 없이 즉시: acceptance criteria 자체가 애매해서 판정이 불가능, 구현이 issue 스코프 밖의 것을 건드림, 통합 테스트 스트림 중 하나가 인프라 문제(계정·secret·환경)로 판단 불가.
```

with:

```markdown
## 4. 리포트 합성 (evaluator 역할)

§1(contract 판정 기록) + §2(agent e2e 자기 요약 + 재확인 결과) + §3(code-reviewer report, agent e2e 결과가 이미 반영됨) 세 가지를 이 세션이 하나의 리포트로 합성한다 — 이건 판단이 아니라 이미 나온 판단들을 압축하는 일이라(어려운 판단은 §1·§3에서 강한 reasoning 모델이 이미 끝냄) Gemini가 해도 된다. PASS/FAIL/ESCALATE 매핑도 아래 고정 규칙을 그대로 적용하는 것이라 이 세션이 직접 낸다:

- **PASS** — code-reviewer report에 Critical/Important finding 없음, contract 판정 승인 상태 유지, agent e2e 통과(자기 요약과 재확인 결과가 일치).
- **FAIL** — 구체적 finding(severity+근거) + 수정 방향을 `orca-workflow`에 반환한다. (재시도는 `orca-workflow`가 관리한다 — 이 스킬은 재-dispatch하지 않는다. `orca-workflow`가 이 리포트를 받아 재시도 카운터를 세고, 필요하면 `orca-task-runner`에 재-dispatch — evaluator가 task-runner를 직접 부르지 않는다.)
- **ESCALATE** — 다음 중 하나면 재시도 없이 즉시: acceptance criteria 자체가 애매해서 판정이 불가능, 구현이 issue 스코프 밖의 것을 건드림, agent e2e가 인프라 문제(계정·secret·환경)로 판단 불가.
```

- [ ] **Step 6: Update 폴백**

Replace:

```markdown
- orca 런타임 불가: coding agent(§1 contract 판정, §2 code review 둘 다)를 orca 없이 **Bash로 직접**(headless, 강한 reasoning 모델 그대로) 실행해 판정·report 회수. 통합 테스트 스트림은 로컬에서 직접 실행하고(e2e·pgTAP은 원래도 모델이 필요 없으므로 그대로 동작) 로그·요약 경로만 기록. 이 evaluator 세션 자체(agy)가 뜨지 않으면 다른 provider로 대체하되, §1·§2의 coding agent는 반드시 이 세션과 다른 provider/모델을 유지한다(같은 세션이 스스로를 판단하지 않도록). 폴백 발동은 사용자에게 보고.
```

with:

```markdown
- orca 런타임 불가: coding agent(§1 contract 판정, §3 code review 둘 다)를 orca 없이 **Bash로 직접**(headless, 강한 reasoning 모델 그대로) 실행해 판정·report 회수. agent e2e(§2)는 로컬에서 Playwright MCP를 붙인 세션으로 직접 실행하고 요약 경로만 기록. 이 evaluator 세션 자체(agy)가 뜨지 않으면 다른 provider로 대체하되, §1·§3의 coding agent는 반드시 이 세션과 다른 provider/모델을 유지한다(같은 세션이 스스로를 판단하지 않도록). 폴백 발동은 사용자에게 보고.
```

- [ ] **Step 7: Run verification again to confirm it passes**

Run:
```bash
grep -c "pg_prove" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
grep -c "pgTAP" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
grep -oE "^## [0-9]+\." /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
```
Expected: first prints `0` (the actual pgTAP execution command is gone); second prints `3` (three remaining plain-English mentions explaining that pgTAP no longer runs here — in the frontmatter description, §0, and §2 — this is expected and correct, not a leftover to clean up); third prints `## 0.` through `## 4.` — same count as before, but now §2 is the agent-e2e test gate and §3 is Diff 리뷰 (confirm by also running `sed -n '/^## 2\./,/^## 3\./p' skills/orca-evaluate/SKILL.md | head -3` and checking it starts with "Test Gate: Agent e2e", and the equivalent for §3 starting with "Diff 리뷰").

- [ ] **Step 8: Commit**

```bash
cd /Users/minchul/Projects/sleeptimegrt-skills
git add skills/orca-evaluate/SKILL.md
git commit -m "$(cat <<'EOF'
refactor: drop e2e/pgTAP from orca-evaluate, run agent-e2e before code review

e2e and pgTAP now run in orca-task-runner's task-level gate before this
skill is even invoked, so orca-evaluate trusts them fully and never
touches that data. Reorder the remaining test gate (agent e2e) ahead of
code review and feed its result into the code-reviewer's task spec, so
review can correlate a diff that looks fine in isolation with runtime
behavior that wasn't. Renumbers §2 (was Diff 리뷰) and §3 (was 통합
테스트 스트림) to match the new order — every internal §N reference in
the file is updated to match.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Fix the stale cross-reference in `model-selection.md` and close out the spec

**Files:**
- Modify: `orca-workflows/model-selection.md` (one paragraph)
- Modify: `docs/superpowers/specs/2026-07-23-orca-generator-evaluator-gate-design.md` (status line)

**Interfaces:**
- Consumes: the final section numbering from Task 3 (§2 = agent e2e, §3 = code review).
- Produces: nothing further — this is the last task.

- [ ] **Step 1: Write the failing verification check**

Run:
```bash
grep -n "diff code review (§2)" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
grep -n "integration-stream log re-check" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
```
Expected: both find a match — this is the stale reference the original design spec assumed didn't exist (it said this file needs no changes; it does, because Task 3 moved code review from §2 to §3, and "integration-stream" implied the e2e/pgTAP/agent-e2e trio that no longer exists here).

- [ ] **Step 2: Fix the paragraph**

Replace:

```markdown
**Exclusion — technical judgment calls do not belong on this axis, even when the calling session itself runs on it.** `orca-evaluate`'s own session defaults to this axis (Gemini) for exactly the reasons above, but its two actual judgment calls — sprint contract approval (§1) and diff code review (§2) of `skills/orca-evaluate/SKILL.md` — are both spawned out to a separate High Risk tier session instead. Don't let "the evaluator is already Gemini" become a reason to also let Gemini make either call — that's the tier this axis is explicitly weaker at (see benchmark table below).

| Provider | Model | Why |
|----------|-------|-----|
| Gemini (agy) | `gemini-3.6-flash` | OSWorld-Verified computer use 78.4%→83%; GDM-MRCR v2 128k long-context 77.3%→91.8% (released 2026-07-21). See `~/.agents/orca-workflows/models/agy.md` for the current smoke-test status before defaulting to it — a new model generation on this axis still needs the same launch verification as any other. |

`orca-evaluate`'s own session, its agent-e2e stream, its integration-stream log re-check, and its final report synthesis (see `skills/orca-evaluate/SKILL.md`) are the current consumers of this axis. Its two spawned coding-agent sub-sessions (contract review, code review) are deliberately *not* consumers — those stay on the High Risk tier above.
```

with:

```markdown
**Exclusion — technical judgment calls do not belong on this axis, even when the calling session itself runs on it.** `orca-evaluate`'s own session defaults to this axis (Gemini) for exactly the reasons above, but its two actual judgment calls — sprint contract approval (§1) and diff code review (§3) of `skills/orca-evaluate/SKILL.md` — are both spawned out to a separate High Risk tier session instead. Don't let "the evaluator is already Gemini" become a reason to also let Gemini make either call — that's the tier this axis is explicitly weaker at (see benchmark table below).

| Provider | Model | Why |
|----------|-------|-----|
| Gemini (agy) | `gemini-3.6-flash` | OSWorld-Verified computer use 78.4%→83%; GDM-MRCR v2 128k long-context 77.3%→91.8% (released 2026-07-21). See `~/.agents/orca-workflows/models/agy.md` for the current smoke-test status before defaulting to it — a new model generation on this axis still needs the same launch verification as any other. |

`orca-evaluate`'s own session (§2 agent-e2e test gate and its raw-trace re-check, plus §4 final report synthesis — see `skills/orca-evaluate/SKILL.md`) is the current consumer of this axis. e2e and pgTAP no longer flow through `orca-evaluate` at all (they're gated in `orca-task-runner` before handoff, deterministically, with no model involved). Its two spawned coding-agent sub-sessions (§1 contract review, §3 code review) are deliberately *not* consumers — those stay on the High Risk tier above.
```

- [ ] **Step 3: Update the design spec status**

In `docs/superpowers/specs/2026-07-23-orca-generator-evaluator-gate-design.md`, replace:

```markdown
**Status**: Approved (brainstorming phase) — pending implementation plan
```

with:

```markdown
**Status**: Implemented — `skills/orca-task-runner/SKILL.md`, `skills/orca-workflow/SKILL.md`, `skills/orca-evaluate/SKILL.md`, `orca-workflows/model-selection.md`
```

- [ ] **Step 4: Run verification again to confirm it passes**

Run:
```bash
grep -n "diff code review (§2)" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
grep -n "integration-stream log re-check" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
grep -c "diff code review (§3)" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
grep -c "Implemented" /Users/minchul/Projects/sleeptimegrt-skills/docs/superpowers/specs/2026-07-23-orca-generator-evaluator-gate-design.md
```
Expected: first two print nothing (no match); third and fourth print `1`.

- [ ] **Step 5: Whole-plan cross-reference sanity sweep**

Run:
```bash
grep -n "§" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-task-runner/SKILL.md
grep -n "§" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-workflow/SKILL.md
grep -n "§" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
grep -n "§" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/model-selection.md
grep -n "pg_prove" /Users/minchul/Projects/sleeptimegrt-skills/skills/orca-evaluate/SKILL.md
grep -n "pgTAP" /Users/minchul/Projects/sleeptimegrt-skills/orca-workflows/models/agy.md
```
Read every `§N` line printed and confirm N refers to a section that exists (in the same file for internal references, in the target file for cross-file ones — `skills/orca-task-runner/SKILL.md §6`, `skills/orca-evaluate/SKILL.md §0/§1/§2/§3/§4`). The `pg_prove` command should print nothing from `orca-evaluate/SKILL.md` (the execution itself is gone, only explanatory mentions of the word "pgTAP" remain, which is correct). `agy.md` should have no pgTAP mentions at all (it never had any — confirmed during Task 3 planning that this file needs no changes).

- [ ] **Step 6: Commit**

```bash
cd /Users/minchul/Projects/sleeptimegrt-skills
git add orca-workflows/model-selection.md docs/superpowers/specs/2026-07-23-orca-generator-evaluator-gate-design.md
git commit -m "$(cat <<'EOF'
docs: fix stale §2 cross-reference in model-selection.md, close out gate-rewiring spec

orca-evaluate's Task 3 renumbering (code review §2 → §3) left this
file's exclusion note pointing at the wrong section, and its
"integration-stream log re-check" phrase still implied the e2e/pgTAP
trio that no longer reaches orca-evaluate at all. The original design
spec assumed this file needed no changes; it did — caught by grep, not
by re-reading the spec's own claim.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

# Model Selection

> verified_at: 2026-07-21

Select the model and effort **before launch**.

Each provider document defines only:

> model × effort → recommended usage

Workflow orchestration (issue-drain, contract 협상, evaluate 판정, task-runner wave 구성)은 `orca-workflow`·`orca-task-runner`·`orca-evaluate`가 관리한다.

---

# Rules

## 1. Classify the task

Choose the highest applicable tier.

| Tier | Typical work |
|-------|--------------|
| **High Risk** | Architecture, auth, RLS, migration, crypto, server logic, production review |
| **Routine** | Feature development, refactor, debugging, testing, code review |
| **Simple** | Formatting, rename, boilerplate, transcription |

If uncertain, choose the higher tier.

---

## 2. Launch with explicit model/effort

Model and effort are fixed at launch.

Examples

- orca terminal argv
- Agent model
- Workflow model

Never assume the CLI automatically chooses effort.

When reusing an existing worker, verify that its launch model still matches the current task.

---

# Default Mapping

## High Risk

Target the highest practical reasoning tier.

| Provider | Model | Effort |
|----------|-------|--------|
| Claude | Opus 4.8 | xhigh |
| Codex | GPT-5.6 Sol | xhigh |
| Gemini | Flash | high (highest available) |

Use these for:

- architecture
- auth
- migration
- security
- production review
- final approval

---

## Routine

Optimize for throughput.

### Claude

Generator

- Sonnet 5 @ high

Advisor / Reviewer

- Opus 4.8 @ xhigh

Preferred pattern:

```
Sonnet 5 (high) 
        ↓
/advisor opus 
```
(opus는 4.8 xhigh 사용)
Do not use Opus as the primary generator unless the task itself is High Risk.

---

### Codex

Generator

- GPT-5.6 Terra @ medium

Escalate to Sol when additional reasoning is required.

---

### Gemini

Generator

- Flash @ high

Preferred when:

- quota efficiency matters
- many parallel workers
- drafting
- routine implementation

Escalate to Codex Terra or Claude when reasoning becomes the bottleneck.

---

## Simple

Use the fastest inexpensive model.

Examples

- Gemini Flash
- Claude Haiku
- lightweight provider defaults

Avoid high reasoning effort.

---

## Computer Use / Long-Context Skeptical Cross-Check

This is a separate axis from the risk tiers above — it doesn't replace them. A task can be Routine risk *and* fall on this axis (e.g. an agent-driven UI e2e test is routine risk but still benefits from computer-use strength).

Use this axis when the task is:

- driving a browser/desktop directly (agent e2e, Playwright-based UI testing)
- re-reading multiple raw logs/artifacts at once, skeptically, to catch what each artifact's own self-summary might miss and to correlate failures across streams

Do **not** reach for this axis just because a stream produces a log. Deterministic, already-structured output (TAP-format pgTAP results, JUnit/JSON test reporters) doesn't need a model at all — parse it with a script. This axis is for cases where trusting a summary at face value is the risk (an agentic session under-reporting a silent failure, or a root cause hidden across several large logs), not a substitute for basic log parsing.

**Exclusion — technical judgment calls do not belong on this axis, even when the calling session itself runs on it.** `orca-evaluate`'s own session defaults to this axis (Gemini) for exactly the reasons above, but its two actual judgment calls — sprint contract approval (§1) and diff code review (§2) of `skills/orca-evaluate/SKILL.md` — are both spawned out to a separate High Risk tier session instead. Don't let "the evaluator is already Gemini" become a reason to also let Gemini make either call — that's the tier this axis is explicitly weaker at (see benchmark table below).

| Provider | Model | Why |
|----------|-------|-----|
| Gemini (agy) | `gemini-3.6-flash` | OSWorld-Verified computer use 78.4%→83%; GDM-MRCR v2 128k long-context 77.3%→91.8% (released 2026-07-21). See `~/.agents/orca-workflows/models/agy.md` for the current smoke-test status before defaulting to it — a new model generation on this axis still needs the same launch verification as any other. |

`orca-evaluate`'s own session, its agent-e2e stream, its integration-stream log re-check, and its final report synthesis (see `skills/orca-evaluate/SKILL.md`) are the current consumers of this axis. Its two spawned coding-agent sub-sessions (contract review, code review) are deliberately *not* consumers — those stay on the High Risk tier above.

---

# Provider Preference

If multiple providers are appropriate:

1. Gemini Flash
2. Claude Sonnet 5
3. Codex Terra

Escalate immediately to higher tiers for:

- architecture
- security
- migration
- production incidents
- final review

---

# Benchmarks (Reference Only)

These values are informational only.

| Model | SWE-Bench Pro |
|--------|---------------|
| Claude Opus 4.8 | Reference anchor |
| GPT-5.6 Sol | 64.6% |
| GPT-5.6 Terra | 63.4% |
| Gemini Flash | 55.1% |

Benchmarks help align tiers.

Model selection should always be based on **task risk**, not benchmark scores alone.

---

# Provider Documents

- Claude Code
  - `~/.agents/orca-workflows/models/claude-code.md`

- Codex
  - `~/.agents/orca-workflows/models/codex.md`

- agy (Gemini)
  - `~/.agents/orca-workflows/models/agy.md`
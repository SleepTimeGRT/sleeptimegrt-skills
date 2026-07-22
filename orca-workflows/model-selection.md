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
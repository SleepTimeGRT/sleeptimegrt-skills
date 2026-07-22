# sleeptimegrt-skills — agent map

Reusable, domain-neutral agent skills for engineering harness work across repositories.
This repository is separate from product-specific skill collections such as `ait-skills`.

This repo is meant to hold skills shared across the coding agents the user runs
day to day: Claude Code, Codex, and Antigravity. Every skill under `skills/` is
authored as a `SKILL.md` with YAML frontmatter (`name` + `description`) and
progressive disclosure. Confirmed 2026-07-22 (see
[vercel-labs/skills](https://github.com/vercel-labs/skills) and the
[Agent Skills spec](https://agentskills.io)): this format is cross-tool as-is —
Claude Code, Codex, and Antigravity (and 70+ other agents) all consume the same
`SKILL.md` without conversion via the `npx skills` installer. The one caveat:
some frontmatter features are Claude-Code-only (`allowed-tools` behavior
details, `context: fork`, hooks) — avoid depending on those in a skill meant to
be portable. See issue #2 for the installer-adoption discussion (catalog vs.
flat layout, publishing this repo via `npx skills add`, plugin-marketplace
distribution).

## Fresh agent protocol

1. Read this file.
2. Read `HANDOFF.md` when it exists; it contains the current work state and verified evidence.
3. For skill creation or substantial skill changes, use the available `skill-creator` guidance before editing.
4. Load only the target skill and the resources directly required for the task.

## Layout

- `skills/<skill-name>/SKILL.md` — skill entry point.
- `skills/<skill-name>/scripts/` — deterministic audit, scaffold, or validation programs.
- `skills/<skill-name>/references/` — detailed guidance loaded only when needed.
- `skills/<skill-name>/assets/` — templates copied into target repositories.
- `tests/` — fixture-based tests for bundled scripts and templates, when introduced.

Create directories lazily. Do not add empty framework folders before a skill needs them.

## Skill rules

- Keep `SKILL.md` concise and procedural. Put trigger conditions in its YAML `description`.
- Use lowercase kebab-case skill names. Keep only `name` and `description` in frontmatter.
- Prefer executable scripts for repeated, deterministic operations instead of reproducing shell snippets in prompts.
- Keep target-repository mutations explicit and reviewable. Audit first; apply only when requested.
- Do not make a user-global runtime dependency necessary for a generated repository to function.
- Do not place auxiliary README, changelog, or process-history files inside a skill folder.

## Gate-output design constraints

For skills that inspect or modify hooks, verify commands, CI, shell scripts, or package scripts:

- Distinguish non-interactive gates from interactive development, deploy, migration, and destructive commands.
- Compact only non-interactive gate output by default. Do not silence interactive progress indiscriminately.
- Preserve `PASS`, `WARN`, `FAIL`, and `SKIP` as distinct outcomes.
- Preserve the original exit code, signal behavior, command order, and fail-fast semantics.
- Keep full diagnostics discoverable through bounded, untracked, worktree-safe logs.
- Treat persisted logs as sensitive assets: use restrictive permissions and review commands for secret output.
- Prefer progressive disclosure: summary first, then targeted `rg`, `tail`, or stage-specific log reads.

## Validation

- Test scripts against temporary fixture repositories before using them on real repositories.
- Cover success, warning, failure, spaces in paths, interrupted execution, worktrees, and log cleanup.
- Compare the gate stages before and after a change so output refactoring cannot silently remove verification.
- Run representative pilots before extracting a shared abstraction or applying changes across repositories.

## Repository operations

- Do not run deploy, release, migration, seed, wipe, or other external-write commands merely to measure output.
- Keep changes to different target repositories in independent commits.
- Do not commit or push this repository unless the user explicitly requests it.

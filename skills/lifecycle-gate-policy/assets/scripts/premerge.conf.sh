# lifecycle-gate-policy: repo config (edit freely) — sourced by scripts/premerge.sh.
# Uncomment and adjust for this repository. Deleting this file falls back to defaults.

# Full verification command (default: "pnpm verify").
#VERIFY_CMD="pnpm verify"

# Merge-blocking e2e command; leave empty if this repo has no e2e gate.
#E2E_CMD="pnpm test:e2e:ci"

# Files matching this regex do not require review (docs-only PRs).
#REVIEW_EXEMPT_REGEX='(^|/)docs/|\.(md|mdx|txt)$'

# Repo-specific additions to the gate-integrity protected set.
#PROTECTED_EXTRA_REGEX='^tools/spec-trace\.mjs$'

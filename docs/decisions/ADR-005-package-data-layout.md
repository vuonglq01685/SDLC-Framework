# ADR-005: package_data Layout

**Status:** Accepted partial (2026-05-07, Story 1.1) — package_data extension deferred to Story 1.16+; back-filled 2026-05-09, Story 1.5; see Consequences.

## Context

Story 1.1 authored `[tool.hatch.build.targets.wheel]` with `packages = ["src/sdlc"]`.
Architecture §276 specifies a `package_data` extension covering non-Python asset trees
(`agents/`, `commands/`, `skills/`, `dashboard/`, `workflows/`, `memory/`,
`claude_hooks/`) that are required by Stories 1.16+ when the first content trees are
authored under `src/sdlc/`.

At Story 1.1 time, none of those directories exist. Story 1.4's "Do NOT create" list
explicitly forbids pre-creating empty stubs. Shipping a `package_data` `include`
pattern over an empty tree is a no-op that accidentally captures future scratch files.

This ADR records the partial decision and the explicit deferral contract so Story 1.16+
knows exactly what to add and why it was deferred.

## Decision

Ship `[tool.hatch.build.targets.wheel]` with `packages = ["src/sdlc"]` only.
The `package_data` extension (covering `agents/`, `commands/`, `skills/`, `dashboard/`,
`workflows/`, `memory/`, `claude_hooks/`) lands in Story 1.16+ when the first content
tree is authored under `src/sdlc/`.

The `pyproject.toml` includes a `# TODO: ADR-005` comment marking the future extension
point for Story 1.16+ operators.

## Alternatives Considered

- **Ship empty placeholder dirs in v0.2**: Rejected — empty directories are not
  portable across hatch + git (git does not track empty directories; hatch
  `packages = ["src/sdlc"]` with empty subdirs would need a `.gitkeep` ceremony
  that adds noise without value until Story 1.16+ lands content).
- **Inline `package_data` upfront with `include = ["**"]` patterns**: Rejected —
  `include = ["**"]` over an empty tree is a no-op but accidentally captures future
  scratch files, test fixtures, or build artifacts that appear under `src/sdlc/` before
  Story 1.16+ has been intentionally scoped.
- **Per-asset-tree `include` patterns authored now**: Rejected — patterns authored
  over non-existent trees are dead code that survives to mislead future maintainers.
  Story 1.16+ authors the patterns at the same time as the asset trees.

## Consequences

- Wheel today contains `sdlc/__init__.py` only (~90 B); no content trees are included.
- `src/sdlc/<content-tree>/**` activation is a one-line `pyproject.toml` edit at
  Story 1.16+ (add `include` patterns under `[tool.hatch.build.targets.wheel]`).
- The `# TODO: ADR-005` comment in `pyproject.toml` is the in-code marker for Story 1.16+
  operators; this ADR is the rationale document.

## Revisit-by

2027-05-01 — or when Story 2A-1 (specialist registry) lands and `src/sdlc/agents/index.yaml`
plus `src/sdlc/agents/**/*.md` require package_data inclusion, whichever first.

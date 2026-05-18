# `/sdlc-bootstrap` — Phase 3 Codebase Scaffolding (FR15)

Scaffolds the initial source tree under `src/` and `tests/` based on Phase 2
architecture decisions. Auto-skips when user source already exists (brownfield no-op).

## Usage

```
sdlc bootstrap
```

## Prerequisites

- Phase 2 signoff must be in state `APPROVED` (run `/sdlc-signoff 2` first)
- `01-Requirement/01-PRODUCT.md` must exist
- `02-Architecture/02-System/ARCHITECTURE.md` must exist (produced by `/sdlc-architect`)

## Auto-Skip Behaviour

If `src/` already contains user code (any file not in the placeholder allowlist
`.gitkeep`, `README.md`), the command exits 0 with message:

```
bootstrap skipped: source already exists at <abs-path>
```

This makes `/sdlc-bootstrap` safe to call on brownfield projects (Epic 3) and
idempotent on post-bootstrap re-runs.

## Outputs

- Files under `src/` and `tests/` as directed by the `code-bootstrapper` specialist
- Journal entry `bootstrap_completed` with `files_written` count

## Error Codes

- `ERR_PHASE2_NOT_APPROVED` — Phase 2 signoff is not approved (and source root is empty)
- `ERR_ARTIFACT_CONTAINS_BOUNDARY` — `PRODUCT.md` or `ARCHITECTURE.md` contains the boundary marker

## Story Reference

Story 2A.15 — `_bmad-output/implementation-artifacts/2a-15-sdlc-bootstrap-phase-3-greenfield-scaffolding.md`

# `/sdlc-ux`

Phase 2 UX track — design tokens, user flows, and screen specs (FR13). Dispatches the
`ux-designer` specialist and writes output files under `02-Architecture/01-UX/`. Requires
Phase 1 signoff to be `APPROVED` before execution.

## CLI

```
sdlc ux
sdlc --json ux
```

## Example

```
sdlc ux
# → 02-Architecture/01-UX/01-tokens.md written
# → 02-Architecture/01-UX/02-flows.md written
# → 02-Architecture/01-UX/03-screens.md written
```

## Behavior

- **Pre-flight**: checks that `.claude/state/state.json` exists and that Phase 1 signoff
  is in state `APPROVED` (via `compute_state(phase=1)`). Refuses with `ERR_PHASE1_NOT_APPROVED` otherwise.
- **Directory creation**: creates `02-Architecture/01-UX/` via `Path.mkdir(parents=True, exist_ok=True)` before dispatch.
- **Dispatch**: dispatches `ux-designer` specialist with Phase 1 product brief as input.
- **Output parsing**: expects a JSON array of `{filename, content}` objects from the specialist (AC2/D1).
- **File writes**: each file is validated (safe filename, `.md` extension, digit-prefixed), then written under `02-Architecture/01-UX/` after running the pre-write hook chain.
- **Journal entries**: emits `agent_dispatched` (×1) + `artifact_written` (×N, one per output file).
- **Parallel reviewer**: deferred to Story 2B.9 per AC3/D1 (`EPIC-2A-DEBT-UX-PARALLEL-REVIEWER`).

## Refusals (exit code 1 with error envelope)

- `ERR_NOT_INITIALIZED` — `.claude/state/state.json` is missing. Run `sdlc init` first.
- `ERR_PHASE1_NOT_APPROVED` — Phase 1 signoff is not `APPROVED`. Run `/sdlc-signoff 1`, approve, then `sdlc scan`.
- `ERR_ARTIFACT_CONTAINS_BOUNDARY` — `01-PRODUCT.md` contains the data/instruction boundary marker.
- `ERR_POSTCONDITION_FAILED` — `ux_dir_non_empty` postcondition failed (specialist returned no files).
- `ERR_HOOK_REJECTED` — phase-gate hook blocked a write (Phase 1 signoff was revoked between pre-flight and write).

## See also

- Story 2A.13 spec: `_bmad-output/implementation-artifacts/2a-13-sdlc-ux-phase-2-ux-track.md`
- Story 2A.8 dispatcher module: `src/sdlc/dispatcher/`
- Story 2A.12 signoff state machine: `src/sdlc/signoff/`
- Architecture §472-475 (Phase 2 directory layout), FR13

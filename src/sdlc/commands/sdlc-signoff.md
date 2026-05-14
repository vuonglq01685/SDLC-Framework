# `/sdlc-signoff <phase>`

Phase signoff draft generation (FR11, FR12). Generates a human-readable `SIGNOFF.md` draft with embedded YAML block for the specified phase. After the human sets `approved: true` and fills in `approved_by`, the next `sdlc scan` validates artifact hashes and writes the canonical signoff record.

## CLI

```
sdlc signoff <phase>
sdlc --json signoff <phase>
```

## Example

```
sdlc signoff 1
# → 01-Requirement/SIGNOFF.md generated with artifact hashes
#   (edit to set approved: true, then run sdlc scan)

sdlc signoff 2
# → 02-Architecture/SIGNOFF.md generated
#   (requires phase 1 signoff to be APPROVED first)
```

## Behavior

- **Phase 1**: enumerates all files under `01-Requirement/` (excluding `SIGNOFF.md` itself), hashes each with SHA-256, writes `01-Requirement/SIGNOFF.md`.
- **Phase 2**: enumerates all files under `02-Architecture/` (excluding `SIGNOFF.md` itself); requires Phase 1 signoff to be `APPROVED`.
- Artifacts sorted lexicographically by POSIX path for byte-stable, deterministic output.
- Re-running overwrites the existing draft and resets `approved: false` unconditionally.
- Once a phase is `APPROVED`, re-running is refused with `ERR_PHASE{N}_ALREADY_APPROVED`.
- No AI dispatch in v1 (AC1/D1); specialist content deferred to Story 2B.8.

## Signoff workflow

1. Run `sdlc signoff <phase>` → generates `SIGNOFF.md`
2. Review artifact list; edit `approved: true` and fill in `approved_by: <your-name>`
3. Run `sdlc scan` → validates hashes and writes canonical `.claude/state/signoffs/phase-<N>.yaml`

## Refusals (exit code 1 with error envelope)

- `ERR_NOT_INITIALIZED` — `.claude/state/state.json` is missing. Run `sdlc init` first.
- `ERR_USER_INPUT` — `phase` is not 1 or 2, or the phase directory does not exist.
- `ERR_NO_ARTIFACTS` — phase directory exists but has no artifacts. Run phase commands first.
- `ERR_PHASE1_NOT_APPROVED` — trying to sign off phase 2 before phase 1 is APPROVED.
- `ERR_PHASE1_ALREADY_APPROVED` / `ERR_PHASE2_ALREADY_APPROVED` — phase is already APPROVED; use `sdlc replan` to invalidate before regenerating.

## See also

- Story 2A.12 spec: `_bmad-output/implementation-artifacts/2a-12-sdlc-signoff-generate-draft-sign-validate.md`
- Story 2A.7 signoff state machine: `src/sdlc/signoff/`
- Story 2A.8 `sdlc start` for the Phase 1 entry point
- Architecture §854-858, §1141-1142 (FR11/FR12)

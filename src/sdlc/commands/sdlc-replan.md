# `/sdlc-replan` — Mark stale + invalidate downstream signoffs (FR4)

**Story 2A.19** | Required option: `--scope=<repo-relative-POSIX-path>`

## Usage

```
sdlc replan --scope=02-Architecture/02-System/ARCHITECTURE.md
sdlc replan --scope=01-Requirement/01-PRODUCT.md
```

## What it does

`sdlc replan` declares that an upstream artifact has changed in a way that
invalidates prior decisions. It:

1. Validates the scope path is a safe repo-relative POSIX path under a known phase directory
2. Computes all downstream phase artifacts (phase-based, AC2/D1)
3. Journals a `replan_invalidated` event recording the dirty set
4. Invalidates all `APPROVED` phase signoffs at phase >= scope_phase (phases 1 and 2 only)
5. Journals one `signoff_invalidated` entry per invalidated phase
6. Emits a JSON success envelope

## Design decisions

- **AC2/D1 (phase-based downstream)**: downstream = all files under phase directories
  numerically greater than `scope_phase`. Tracks as `EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG`.
- **AC2/D2 (dirty record location)**: dirty set lives in the `replan_invalidated`
  journal payload. Projection into `state.json` deferred as `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION`.
- **AC6/D1 (trace passthrough)**: `sdlc trace <task>` surfaces `replan_invalidated`
  entries postdating the task's first journal entry.
- **No workflow YAML, no specialist**: `sdlc replan` is pure state machinery.

## Phase-to-directory mapping

| Phase | Directory |
|-------|-----------|
| 1 | `01-Requirement/` |
| 2 | `02-Architecture/` |
| 3 | `03-Implementation/` |

Phase 3 has no signoff — a `scope_phase=3` replan records the dirty event but
invalidates no signoff records.

## JSON output (`--json`)

```json
{
  "command": "replan",
  "scope": "02-Architecture/02-System/ARCHITECTURE.md",
  "scope_phase": 2,
  "downstream_count": 12,
  "invalidated_phases": [2],
  "outcome": "success"
}
```

## Error codes

| Code | Meaning |
|------|---------|
| `ERR_NOT_INITIALIZED` | `.claude/state/state.json` absent — run `sdlc init` first |
| `ERR_USER_INPUT` | Invalid `--scope`: absolute path, backslash, `..` traversal, missing file, or unknown phase dir |
| `ERR_JOURNAL_APPEND_FAILED` | Journal write failed |

## Debt

- `EPIC-2A-DEBT-REPLAN-FINE-GRAINED-DAG` — artifact-level provenance traversal
- `EPIC-2A-DEBT-REPLAN-DIRTY-PROJECTION` — fold `replan_invalidated` into `state.json`

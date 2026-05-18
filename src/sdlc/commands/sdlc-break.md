# `/sdlc-break <STORY-id>` — Phase 3 Task Generation (FR16)

Breaks an active story into implementation tasks under `03-Implementation/tasks/<STORY-id>/`.
Only the active story is broken; future stories remain at story level (just-in-time task
generation, avoiding stale future-task drift).

## Usage

```
sdlc break <STORY-id>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `STORY-id` | The active story identifier (e.g. `EPIC-foo-S01-bar`). Must match `STORY_ID_REGEX`. |

## Prerequisites

- Phase 2 signoff must be in state `APPROVED` (run `/sdlc-signoff 2` first)
- `01-Requirement/01-PRODUCT.md` must exist
- The story JSON file must exist at `01-Requirement/05-Stories/<EPIC-id>/<STORY-id>.json`
- The story's `status` field must be `"in-progress"` (**v1 manual requirement** — see note below)

## Manual Status Requirement (v1)

Until Story 2A.18 (`/sdlc-next`) lands, you must **manually edit** the story JSON file
to set `"status": "in-progress"` before running `/sdlc-break`. This is an acknowledged
debt item (`EPIC-2A-DEBT-BREAK-MANUAL-STATUS-FLIP`).

To activate a story for breaking:

```bash
# Edit the story JSON file and set status field:
# "status": "in-progress"
$EDITOR 01-Requirement/05-Stories/EPIC-foo/EPIC-foo-S01-bar.json
```

Then run:

```bash
sdlc break EPIC-foo-S01-bar
```

## Idempotency

Running `/sdlc-break` twice on the same story is refused if `03-Implementation/tasks/<STORY-id>/`
already contains task files matching `T<NN>-*.json`. Use `/sdlc-next` to advance through tasks.

## Outputs

- Task JSON files at `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json`
- Journal entries: `agent_dispatched` → `artifact_written` (×N) → `story_broken_into_tasks`

## Error Codes

| Code | Meaning |
|------|---------|
| `ERR_PHASE2_NOT_APPROVED` | Phase 2 signoff is not approved |
| `ERR_ARTIFACT_CONTAINS_BOUNDARY` | `PRODUCT.md` or story JSON contains the boundary marker |

## Story Reference

Story 2A.16 — `_bmad-output/implementation-artifacts/2a-16-sdlc-break-active-story-only-task-generation.md`

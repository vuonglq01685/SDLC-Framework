# `/sdlc-task <TASK-id>` — Phase 3 TDD Pipeline (FR17)

Advances a task by **exactly one stage** per invocation through the 5-stage TDD pipeline:

```
pending → write-tests → write-code → review → done
```

Re-invoke to drive each stage; `/sdlc-next` (Story 2A.18) advances all pending tasks.

## Usage

```
sdlc task <TASK-id>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `TASK-id` | The task identifier (e.g. `EPIC-foo-S01-bar-T01-design-data-model`). Must match `TASK_ID_REGEX`. |

## Prerequisites

- Phase 2 signoff must be in state `APPROVED`
- The story's task JSON must exist at `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json`
  (run `/sdlc-break <STORY-id>` first)

## Stage Machine (one stage per invocation)

| Current Stage | Specialist Dispatched | Files Written | Next Stage |
|--------------|----------------------|---------------|------------|
| `pending` | `test-author` | `tests/**` (must report `tests_status: "red"`) | `write-tests` |
| `write-tests` | `code-author` | `src/**` (must report `tests_status: "green"`) | `write-code` |
| `write-code` | `code-reviewer` | task JSON (verdict captured) | `review` |
| `review` (approved) | *(none — pure state advance)* | *(none)* | `done` |
| `review` (rejected) | *(refused — must address feedback)* | *(none)* | stays `review` |

## RED→GREEN Gate (AC4/D1)

v1 trusts the specialist's self-reported `tests_status`:

- `test-author` at the `pending → write-tests` stage MUST report `tests_status: "red"`.
  A `"green"` response means tests don't fail first — TDD discipline violated → transition refused.
- `code-author` at the `write-tests → write-code` stage MUST report `tests_status: "green"`.
  A `"red"` response means the implementation didn't turn the suite green → transition refused,
  written code files rolled back.

Debt: `EPIC-2A-DEBT-TASK-REAL-TEST-EXECUTION` — replace with real `pytest` subprocess gate
once `ClaudeAIRuntime` produces real source (Epic 2B).

## Idempotency

Running `/sdlc-task` on a task already at `stage: done` is refused with a non-zero exit.

## Outputs

- Stage-specific files under `tests/**` (test-author) or `src/**` (code-author)
- Updated task JSON at `03-Implementation/tasks/<STORY-id>/T<NN>-<slug>.json`
- Journal entries: `task_stage_advanced` on success, `task_stage_failed` on failure

## Failure Handling

On any transition failure (hook denial, schema error, RED→GREEN gate, rejected review):

- The task JSON `stage` is left unchanged
- Any files written before the failure point are rolled back (unlinked)
- `task_stage_failed` is journaled with the reason
- The CLI exits non-zero with an actionable message naming the next user action

## Error Codes

| Code | Meaning |
|------|---------|
| `ERR_USER_INPUT` | Malformed TASK-id, task JSON missing/unparseable, or identity mismatch |
| `ERR_NOT_INITIALIZED` | Project not initialized (run `sdlc init` first) |
| `ERR_PHASE2_NOT_APPROVED` | Phase 2 signoff is not approved |
| `ERR_ARTIFACT_UNREADABLE` / `ERR_ARTIFACT_CONTAINS_BOUNDARY` | Task JSON undecodable or contains the boundary marker |
| `ERR_TASK_STAGE_FAILED` | A stage transition failed (dispatch, hook, RED→GREEN gate, rejected review) |
| `ERR_INFRASTRUCTURE` / `ERR_SIGNOFF_READ_FAILED` | Workflow/registry load or signoff-state read failed |

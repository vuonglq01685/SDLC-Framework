# `/sdlc-next` — Select and advance the highest-priority ready item (FR18)

**Story 2A.18** | No positional arguments.

## What it does

`sdlc next` inspects the project artifact tree and selects the next item to
advance. It routes based on which phase the project is currently in:

| State | Action |
|-------|--------|
| Phase 1 not started | Print `/sdlc-start "<idea>"` |
| Phase 1 in progress | Print the missing Phase 1 command (`/sdlc-epics`, `/sdlc-stories`, `/sdlc-signoff 1`) |
| Phase 2 in progress | Print the missing Phase 2 command (`/sdlc-architect`, `/sdlc-signoff 2`) |
| Phase 2 approved — task ready | **Auto-dispatch** `/sdlc-task <TASK-id>` in-process |
| All tasks done or blocked | Print a reason string (Epic 4 STOP placeholder) |

## Design decisions

- **AC1/D1**: module is `cli/next_.py` (trailing underscore — `next` is a Python
  builtin; mirrors `break_.py` precedent from Story 2A.16).
- **AC2/D1**: phase-aware resolver (`_next_resolver.py`) reads disk state directly;
  does NOT drive from `state.json` (v1 projection has empty tasks map).
  Tracked as `EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION` for when the full projection lands.
- **AC3/D1**: Phase 3 auto-dispatch calls `run_task(ctx=ctx, task_id=...)` in-process;
  exit code and output reflect the underlying `/sdlc-task` run.

## No workflow YAML, no specialist

`sdlc next` is a read-and-route command like `sdlc scan` and `sdlc status`.
It dispatches **no specialist of its own** and touches **no specialist registry**.

## JSON output (--json)

### Phase 1/2 item selected (print path)
```json
{"command": "next", "next_action": "command", "phase": 1,
 "suggested_command": "/sdlc-signoff 1", "reason": "phase 1 unsigned"}
```

### No ready items
```json
{"command": "next", "next_action": "none", "reason": "all tasks complete",
 "blockers": {"blocked_by_deps": 0, "awaiting_signoff": 0}}
```

### Phase 3 task selected
The envelope from the underlying `/sdlc-task` run is surfaced directly.

## Error codes

| Code | Meaning |
|------|---------|
| `ERR_NOT_INITIALIZED` | `.claude/state/state.json` absent — run `sdlc init` first |
| `ERR_SIGNOFF_READ_FAILED` | Could not read a phase signoff record |

## Debt

- `EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION` — refactor to consume `state.json` once
  `EPIC-2A-DEBT-TASK-STATE-PROJECTION` lands the task projection
- `EPIC-2A-DEBT-NEXT-PRIORITY-RANKING` — true P0–P3 priority ranking deferred to Epic 4/5

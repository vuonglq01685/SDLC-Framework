# Codemap: sdlc.state

**Story:** 1.12 — State Projection from Journal + Replay Property Test
**ADR:** [ADR-015](../decisions/ADR-015-state-projection-from-journal.md)
**Cross-link:** [sdlc.journal codemap](journal.md) — state depends on journal (Decision B5)

## Files

| File | Purpose |
|------|---------|
| `src/sdlc/state/__init__.py` | Package init; semantic-order `__all__`; Windows stubs for POSIX-only functions |
| `src/sdlc/state/model.py` | Minimal `State` pydantic v2 model (frozen); `schema_version`, `next_monotonic_seq`, `epics` |
| `src/sdlc/state/atomic.py` | POSIX-only atomic write protocol (`write_state_atomic`, `write_state_atomic_sync`, `read_state`); Story 1.10 |
| `src/sdlc/state/projection.py` | **Story 1.12** — pure-function `project_from_journal` + private `_project_entries` reducer |
| `tests/unit/state/test_state_projection.py` | Unit tests for projection: 13 cases (11 cross-platform, 2 POSIX-only) |
| `tests/property/test_replay_invariant.py` | **Story 1.12** — hypothesis replay invariant; 4 properties (1 main + smoke + drift + idempotent) |

## Public API (`sdlc.state.__all__`)

```python
("State", "write_state_atomic", "write_state_atomic_sync", "read_state", "project_from_journal")
```

Semantic order: model → write-async → write-sync → read → projection.

## Key Decisions

- `project_from_journal` is **cross-platform** (no fcntl/O_APPEND); reads via `iter_entries`.
- `_project_entries` is a **private test seam** (single underscore, not in `__all__`).
- `MODULE_DEPS["state"]` gains `"journal"` in Story 1.12 — see ADR-015.
- Property test uses an **independent oracle reducer** (`_oracle_reduce` in test file) for
  differential testing — do not refactor to import `_project_entries`.

# Codemap: sdlc.engine

**Story:** 1.15 — Engine Scanner Skeleton (Idempotent, Side-Effect-Free)
**ADR:** [ADR-018](../decisions/ADR-018-engine-scanner-skeleton.md)
**Cross-links:** [sdlc.state codemap](state.md) — scanner returns `State`; [sdlc.ids](../../src/sdlc/ids/) — regex + parsers consumed by scanner

## Files

| File | Purpose |
|------|---------|
| `src/sdlc/engine/__init__.py` | Package init; re-exports `scan` as the sole public API surface in v1 |
| `src/sdlc/engine/scanner.py` | **Story 1.15** — pure `scan(project_root: Path) -> State`; walks artifact tree, no writes |

## Public API (`sdlc.engine.__all__`)

```python
("scan",)
```

`scan(project_root: Path) -> State` — walks `01-Requirement/04-Epics/`, `01-Requirement/05-Stories/`, and `03-Implementation/tasks/`; returns a deterministic `State` projection. Zero I/O writes. Raises `StateError` only on programmer errors (non-absolute path, path-is-a-file); missing directories yield an empty partial State.

## Scanner Contract

- **Pure**: zero writes, zero subprocess calls, zero network I/O, zero `os.environ` reads.
- **Total**: returns `State` for every reachable input (empty dir, partial layout, fully-populated project).
- **Deterministic**: `json.dumps(scan(p).model_dump(mode="json"), sort_keys=True, ...)` is byte-equal across back-to-back calls on the same on-disk state.
- **Portable**: no `fcntl`, `O_APPEND`, or parent-dir fsync — runs on Windows and POSIX equally.

## Performance Gate (NFR-PERF-1)

| Scenario | Budget | Corpus |
|----------|--------|--------|
| Cold start | < 2.0 s | 4 epics × 50 stories × 5 tasks = 200 stories + 1000 tasks |
| Warm cache | < 100 ms | same corpus, OS file cache pre-warmed |

Gate enforced by `tests/benchmark/test_scan_perf.py` via `pytest-benchmark` on `ubuntu-latest` python 3.12 in CI.

## Filesystem Layout Scanned

```
<project_root>/
├── 01-Requirement/
│   ├── 04-Epics/          # EPIC-<slug>.json → state.epics
│   └── 05-Stories/
│       └── <EPIC-id>/     # <STORY-id>.json  → state.stories
└── 03-Implementation/
    └── tasks/
        └── <STORY-id>/    # <TASK-id>.json   → state.tasks
```

Files not matching `EPIC_ID_REGEX` / `STORY_ID_REGEX` / `TASK_ID_REGEX` are skipped (logged at WARN). Hidden files (`.gitkeep`, `.DS_Store`) and non-`.json` files are skipped silently.

## Key Decisions

- Scanner is **read-only**; `cli/scan.py` (Story 1.17) wraps it with `write_state_atomic_sync` + `journal.append_sync`.
- `MODULE_DEPS["engine"].depends_on` includes `"ids"` (widened in Story 1.15) for `parse_epic_id/_story_id/_task_id`.
- `State` model extended additively in Story 1.15: `phase: int = 1`, `stories: dict`, `tasks: dict`. `schema_version` unchanged at `1`.
- Benchmark corpus is **runtime-scaffolded** (never committed); see `tests/benchmark/conftest.py`.

## Future Submodules (out of scope for v1.15)

| File | Story | Purpose |
|------|-------|---------|
| `src/sdlc/engine/auto_loop.py` | 4.1 | Auto-loop orchestration (scan → dispatch → STOP check) |
| `src/sdlc/engine/stop_triggers.py` | 4.x | Configurable STOP conditions |
| `src/sdlc/engine/logging.py` | 2A.x | structlog wrapper (stdlib `logging` used until then) |

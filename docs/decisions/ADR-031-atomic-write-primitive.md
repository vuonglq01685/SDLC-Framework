# ADR-031: Atomic Raw-Text Write Primitive (`sdlc.concurrency.io_primitives.atomic_write`)

**Status:** Accepted (2026-05-21, prep-sprint C1).
**Source:** Epic 2A retrospective §6.2 D1 + §7.1 C1 — "Atomic raw-text write primitive
(`engine/io_primitives.py`) — closes Epic 1 D3 + Epic 2A WRITE-PRIMITIVE".
**Closes:** `EPIC-1-D3-EINTR-RETRY`, `EPIC-2A-D1-WRITE-PRIMITIVE`.

## Context

Two parallel write infrastructures existed at end of Epic 2A:

1. **`src/sdlc/state/atomic.py`** — a chaos-tested 7-step POSIX protocol (open tmp → write →
   fsync tmp → flock → rename → fsync parent dir) that is **JSON-specific** (canonicalises
   `State` and raw-dict payloads) and **state.json-specific** (`STATE_FILE_NAME`,
   `STATE_LOCK_SUFFIX`). It does **not** retry on `EINTR` (the Epic 1 D3 debt) — any
   `OSError` from `os.write` immediately raises `StateError`.

2. **17 ad-hoc `Path.write_text(content, encoding="utf-8")` callsites** across
   `dispatcher/_panel_helpers.py` (the canonical `EPIC-2A-DEBT-WRITE-PRIMITIVE` marker
   site at line 565) and 8 `cli/_*_pipeline.py` + `cli/research.py` files. Every Epic 2A
   pipeline story (2A.3, 2A.8, 2A.11, 2A.13, 2A.14, 2A.15, 2A.16, 2A.17) added one or two
   raw-text writes that look atomic to the reader but are not (mid-write process kill
   leaves a partial file).

The Epic 2A retro top-of-mind worry (Pattern 2 — Systemic Repetition of Non-Atomic Write)
quantified the systemic risk: 7+ stories shipped non-atomic writes; the underlying root
cause is the absence of a generic raw-text atomic primitive that callsites would naturally
reach for.

## Decision

Ship a new `atomic_write(path, content, *, encoding="utf-8")` primitive that:

1. **Reuses the same 7-step POSIX protocol** as `state/atomic.py`.
2. **Adds explicit `EINTR` retry** on `os.write` AND `os.replace`, with a `_MAX_EINTR_RETRIES`
   = 16 budget. Beyond 16 consecutive EINTRs is treated as a pathological signal-storm and
   re-raised.
3. **Lives in `src/sdlc/concurrency/`** (not `src/sdlc/engine/`) so both `dispatcher/` and
   `cli/` can import it — both depend on `concurrency` per the module-boundary table;
   neither may import `engine/`. Placement also makes semantic sense: atomic-write is a
   concurrency-safety primitive (preventing partial writes) adjacent to `concurrency.file_lock`.
4. **Re-raises `OSError`** (not a wrapped `StateError` / new `IOPrimitivesError`) — callsites
   in pipeline code do not have a "state error" vocabulary, and standard-library `OSError`
   matches what Python developers already expect from atomic-write libraries.
5. **Keeps the `encoding` parameter** (default `utf-8`) plus a sibling `atomic_write_bytes`
   for the rare binary case (Phase-3 task-runner artefacts).

### Migration (this commit)

Migrated 17 callsites across 9 files to `atomic_write`:

| File | Callsites |
|---|---|
| `dispatcher/_panel_helpers.py` | 1 (canonical EPIC-2A-DEBT-WRITE-PRIMITIVE marker site) |
| `cli/_architect_pipeline.py` | 2 |
| `cli/_bootstrap_pipeline.py` | 2 |
| `cli/_break_pipeline.py` | 2 |
| `cli/_epics_pipeline.py` | 2 |
| `cli/_stories_pipeline.py` | 2 |
| `cli/_task_pipeline.py` | 3 (incl. rollback restore path) |
| `cli/_ux_pipeline.py` | 2 |
| `cli/research.py` | 1 |

Not migrated (explicit out-of-scope decisions):

- `cli/scan.py:54` — state.json fallback already noqa'd ("Windows non-atomic fallback;
  POSIX-only atomic protocol unavailable"). Owned by `state/atomic.py`.
- `cli/init.py:167` — `write_bytes` copying templates from package_data; different
  semantics (copy, not author-write).
- `cli/start.py:137`, `cli/_verify_dispatch.py:88`, `cli/_task_pipeline_mocks.py:62` —
  mock-runtime fixture authors that only exist in the test harness. Migration deferred
  to a future round; non-production paths.

## Alternatives Considered

- **Modify `state/atomic.py` in place to add EINTR retry + generalise to any path.**
  Rejected: state/atomic.py is the centre of an 18-test chaos suite (kill-points × seeds)
  and is JSON-canonicalisation-specific. Churning it during prep-sprint risks invalidating
  chaos coverage that the team explicitly does not want to regress before Story 2B.1.

- **Move atomic_write to `engine/io_primitives.py` (original Epic 2A retro phrasing).**
  Rejected after RED-checkpoint review: `dispatcher.depends_on` does NOT include `engine`;
  the canonical EPIC-2A-DEBT-WRITE-PRIMITIVE callsite at `_panel_helpers.py:565` lives in
  `dispatcher/` and cannot import from `engine/`. Relocation to `concurrency/` (which both
  dispatcher AND cli depend on) is mandatory; the retro phrasing pre-dated the
  module-boundary refinement.

- **Wrap `OSError` into a new `IOPrimitivesError`.** Rejected: adds a new error type to
  `sdlc.errors` without a clear consumer; callsites in pipeline code already catch
  `(OSError, WorkflowError, SpecialistError)` and would either ignore the new type or
  awkwardly catch both. Standard-library `OSError` is the lowest-friction choice.

- **Honour `encoding="utf-8"` everywhere by hardcoding it.** Rejected: leaving the
  parameter retains future flexibility (e.g., when a Phase-3 specialist needs latin-1
  for legacy artefact ingestion); the default value is utf-8 so 100% of current callsites
  remain a no-arg use case.

## Consequences

- **+** All 17 production raw-text writes are now mid-process-kill-safe and EINTR-safe.
  A signal interrupt during write or rename no longer crashes the pipeline; partial files
  no longer ship to operators reading the artifact.
- **+** Pattern 2 (systemic non-atomic write) closed: every new pipeline story author
  reaches for `atomic_write` instead of `.write_text`, and code-review subagents can flag
  the pattern automatically when they see raw `.write_text` in dispatch contexts.
- **+** `EPIC-1-D3-EINTR-RETRY` carry-forward closed — the EINTR debt that had survived
  two epics is now resolved at the primitive layer that both old and new callsites use.
- **+** `state/atomic.py` is untouched; its chaos-test coverage remains intact.
- **−** Two atomic-write primitives now coexist (`state.atomic.write_state_atomic*` for
  JSON state, `concurrency.io_primitives.atomic_write*` for raw text). Future refactor
  to share the 7-step body via a common helper is deferred — tracked as
  `EPIC-2B-DEBT-SHARE-ATOMIC-PROTOCOL` (a follow-up `concurrency/_write_protocol.py`
  that both modules can call).
- **−** The three mock-runtime fixture authors (`cli/start.py:137`,
  `cli/_verify_dispatch.py:88`, `cli/_task_pipeline_mocks.py:62`) still use raw
  `Path.write_text`. They never run in production (test harness only) but the inconsistency
  is real. Tracked as `EPIC-2B-DEBT-MOCK-FIXTURE-NON-ATOMIC` for a future cleanup pass.

## Migration plan (for future stories)

| When | Action | Owner |
|---|---|---|
| Now (this ADR) | Primitive shipped, 17 production callsites migrated, two debt items closed | prep-sprint C1 |
| Story 2B.1 (ClaudeAIRuntime) | Use `atomic_write` for any new specialist artifact write; do not reach for `Path.write_text` | Charlie |
| Future refactor (no story yet) | Extract shared `concurrency/_write_protocol.py` so `state/atomic.py` + `io_primitives.py` share the 7-step body | Architect-led, post-Epic-2B |
| Future cleanup (no story yet) | Migrate the three mock-fixture authors so the codebase has zero `Path.write_text` outside `state/atomic.py`'s scope and template-copy paths | (any author touching the test harness) |

## Revisit-by

After Story 2B.1 lands. Confirm `atomic_write` is the universal raw-text write primitive
across the new ClaudeAIRuntime paths AND that the deferred mock-fixture cleanup is
prioritised in the Epic 2B retrospective if it has not landed by then.

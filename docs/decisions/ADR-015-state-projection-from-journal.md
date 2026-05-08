# ADR-015: State Projection from Journal

**Status:** Accepted
**Date:** 2026-05-08
**Story:** 1.12

## Context

Decision B5 (Architecture §349) declares that `state.json` is a deterministic projection of the
journal — the journal is the sole source of truth. Decision B4 (Architecture §348) defers snapshot
caching to v1.x, so v1 always replays the full journal from entry 0. Architecture §220 (Murat's
added invariant) requires: `replay(journal[0:k]) == state_at_step_k` for every `k`, verified by
a hypothesis property test (≥1000 examples per CI run).

Before Story 1.12, the architecture stated "state is a projection" but no code computed the
projection. The `MODULE_DEPS["state"]` boundary table (scripts/check_module_boundaries.py:50-53)
did not list `"journal"` as a dependency of `"state"`, creating an architectural-intent vs
boundary-table discrepancy. Story 1.12 resolves this by implementing the projection primitive
and reconciling the dependency graph.

Architecture §1059 lists `project_from_journal` as part of `state/`'s public API, confirming
the primitive/CLI split: this story ships the pure projection function; `sdlc rebuild-state`
(FR35) is deferred to Story 1.20.

## Decision

1. **Pure-function projection**: `project_from_journal(journal_path: Path) -> State` in
   `src/sdlc/state/projection.py`. Reads via `sdlc.journal.iter_entries` (cross-platform);
   no I/O writes, no global mutation, no subprocess.

2. **Per-kind reducer dispatch**: `_project_entries(entries: Iterable[JournalEntry]) -> State`
   folds entries with these rules for v1:
   - All kinds advance `next_monotonic_seq = max(next_seq, entry.monotonic_seq + 1)`.
   - `kind == "state_mutation"` with `target_id` matching `^epic-\d+$` updates `state.epics`.
   - Unknown kinds advance `next_monotonic_seq` only (permissive — kind drift within a schema
     version must not break replay of historical journals).

3. **Schema-version drift fail-loud**: if `entry.schema_version != 1`, the projection raises
   `JournalError` with the exact message `"unknown schema_version=N for kind=X; run sdlc migrate-vN"`.
   This is the forward-contract for the `migrate-vN` CLI (FR49, deferred). Future stories
   implementing `sdlc migrate-vN` will key off this exact wording.

4. **Dual-defence for schema_version**: `JournalEntry.schema_version: Literal[1] = 1` rejects
   `schema_version != 1` at pydantic parse time. The projection's check is the second line of
   defence for the case where a future build extends the Literal range — projection still
   recognizes only v1.

5. **MODULE_DEPS["state"] gains "journal"**: `src/sdlc/state/projection.py` imports
   `from sdlc.journal import iter_entries`. Adding `"journal"` to `MODULE_DEPS["state"].depends_on`
   aligns the boundary table with the architectural intent (Architecture §1059, Decision B5).
   The directed edge `state → journal` is acyclic (validated by `_validate_no_cycles`).

6. **Differential property test**: `tests/property/test_replay_invariant.py` implements an
   independent oracle reducer `_oracle_reduce` (does not import `_project_entries`). Hypothesis
   generates arbitrary journal sequences and asserts
   `project_from_journal(journal[:k]).model_dump(mode="json") == _oracle_reduce(entries[:k]).model_dump(mode="json")`
   for every prefix `k`. Runs ≥1000 examples per CI run.

7. **`_project_entries` as test seam**: single-underscore prefix, importable from
   `sdlc.state.projection`, NOT in `__all__`. Future stories MAY use this seam but must treat
   it as semi-stable — moving it requires coordinated update to property tests.

## Consequences

- **Forward-compat migration contract**: the `"run sdlc migrate-vN"` phrase in the error
  message is a reserved name. Stories implementing `cli/migrate.py` (FR49) will key off this.
- **Permissive unknown-kind reducer**: future kinds can be added without breaking replay of
  historical journals.
- **Snapshot caching deferred**: the pure-function design makes memoizing on
  `(journal_path, mtime)` trivial; see Architecture §326 for the decision to defer.
- **Known v1 gap**: hash-chain validation across consecutive entries
  (`entry[i+1].before_hash == entry[i].after_hash`) is NOT performed by the projection.
  `JournalEntry` carries `before_hash`/`after_hash` but the chain is not validated here.
  Add to future audit-integrity story.
- **`_project_entries` semi-stable**: future stories extending the reducer (e.g., adding
  story-/task-projection when those fields exist on `State`) must update the oracle in
  `test_replay_invariant.py` in the same commit. The differential test catches divergence.

## References

- ADR-013 (atomic state write protocol) — Story 1.10
- ADR-014 (append-only journal protocol) — Story 1.11
- Architecture §220, §348, §349, §382, §601-§606, §845, §1059
- Decision B4, B5, F3

# ADR-032: `journal.append_with_seq_alloc` — Cross-Process Atomic Seq Allocation

**Status:** Accepted (2026-05-21, prep-sprint C2).
**Source:** Epic 2A retrospective §6.2 D2 + §3 Pattern 3 — Process-Local Seq Allocation Race
(5 stories affected: 2A.3, 2A.8, 2A.11, 2A.14, 2A.17).
**Closes:** `EPIC-2A-D2-PANEL-V1-PROCESS-LOCAL-SEQ`.

## Context

The Epic 2A `_allocate_seq` allocator in `dispatcher/_panel_helpers.py:143` is
**process-local**: it computes `max(disk_highest, last_allocated_in_this_process) + 1` under
a per-journal `asyncio.Lock`. The asyncio lock serialises allocations *within* one Python
process but provides no coordination across processes.

The race:

```
Process P1:  _allocate_seq() reads disk → highest=5 → returns 6 → journal_append(entry seq=6) [flock acquired by append()]
Process P2:  _allocate_seq() reads disk → highest=5 → returns 6 → journal_append(entry seq=6) [waits for P1 lock, then succeeds]
                                                                                              ^^^^ DUPLICATE SEQ
```

`journal.append()` already wraps writes in `file_lock(_lock_path_for(journal_path))`, but
the per-append flock protects the WRITE — not the READ that preceded it. The seq is computed
*outside* the lock and committed *inside*; two processes can both leave the read with the
same value before either enters the write.

Five Epic 2A stories cited this debt as
`EPIC-2A-DEBT-PANEL-V1-PROCESS-LOCAL-SEQ`. The fix needs to be additive — `_allocate_seq`
is reachable from many call sites and ripping it out would require rewriting every dispatch
audit row at once.

## Decision

Ship `journal.append_with_seq_alloc(journal_path, entry_factory)` as a new high-level
helper that holds the journal write flock ONCE across the full read→build→append cycle:

```python
async with file_lock(_lock_path_for(journal_path)):
    highest = _read_highest_seq(journal_path)
    seq = highest + 1
    entry = entry_factory(seq)
    if entry.monotonic_seq != seq:
        raise _je("factory_seq_mismatch", ...)
    _append_protocol_body(entry, journal_path)
    return seq
```

This is **architecturally race-free**: only one process can be inside the flock at a time, so
the read+build+append sequence is atomic across processes. Returns the allocated seq for
callers to log or correlate.

The factory contract:

- Pure + fast (no IO, no further journal interactions).
- Builds an entry whose `monotonic_seq == seq` (the argument it receives).
- Defensive `factory_seq_mismatch` check catches contract violations with a focused error
  (the protocol body's `seq <= highest` invariant would catch the same bug but reads as
  "stale seq" which is operationally opaque).

Windows fallback in `sdlc/journal/__init__.py` raises `JournalError` with
`step="windows_unsupported"` — same pattern as the existing `append` / `append_sync` /
`allocate_next_seq_for_append_sync` Windows stubs.

## Migration plan

This ADR does NOT migrate the 5 existing callsites. They each interleave the allocate and
append with significant non-trivial work (dispatch outcomes, payload assembly, conditional
journal emissions) that does not cleanly fit the `factory(seq) -> entry` signature without
restructuring the surrounding code.

**Forward rule:** New code emitting journal entries SHOULD use `append_with_seq_alloc`
unless interleaving requires the lower-level `_allocate_seq` + `append` pair. Story 2B.1
(ClaudeAIRuntime) uses the new helper for all real-runtime dispatch journal emissions from
day one.

**Legacy migration:** Tracked as `EPIC-2B-DEBT-MIGRATE-PROCESS-LOCAL-SEQ-CALLSITES`. The
5 affected sites are listed below; each is a candidate for restructuring when its
surrounding story is next touched (e.g. as part of 2B.1 / 2B.3 / 2B.6 work).

| File | Line | Story | Notes |
|---|---|---|---|
| `dispatcher/_panel_helpers.py` | 220, 251, 445, 492, 569 | 2A.3 + 2A.8 | Synthesizer + panel dispatch journal rows |
| `cli/_epics_pipeline.py` | 234-ish | 2A.11 | artifact_written + dispatch_attempt rows |
| `cli/_stories_pipeline.py` | similar | 2A.11 | analogous |
| `cli/_architect_pipeline.py` | 224, 291-ish | 2A.14 | Phase-2 dispatch rows |
| `cli/_task_pipeline.py` | task_stage_advanced + task_stage_failed | 2A.17 | TDD pipeline stage transitions |

## Alternatives Considered

- **Promote `_allocate_seq` itself to acquire the journal flock.** Rejected: the existing
  `_allocate_seq` is reached from N callsites with varying expectations (some hold the lock
  from outside, some don't, some call it in non-async paths). Changing its locking contract
  retroactively risks deadlocks and is a wholesale-rewrite trigger, not a primitive add.
- **Provide a context-manager API `with journal_lock(path): seq = ...; append(...)`.**
  Rejected after RED-checkpoint: makes callers responsible for honouring the lock semantics,
  which is exactly the discipline that has already drifted across 5 stories. A focused
  factory-based API moves the discipline into the helper.
- **Cross-process integration test (subprocess spawn).** Rejected for C2: the existing
  `test_cross_process_contention` is a pre-existing xfail under EPIC-2A-DEBT-001; adding
  another flaky subprocess test would expand scope without proving the design. Architectural
  proof (one flock around read+build+write) is the load-bearing argument; chaos tests can
  validate the property end-to-end in a future story.

## Consequences

- **+** Architectural cross-process atomicity for new journal-emitting code paths.
  ClaudeAIRuntime (2B.1) ships with no PANEL-V1 risk.
- **+** Existing low-level `_allocate_seq` + `append` pair untouched; current dispatch
  path behaviour preserved.
- **+** Defensive `factory_seq_mismatch` error is operator-friendly when callers misuse the
  factory contract.
- **−** Two ways to allocate a seq now coexist (`_allocate_seq` + `append_with_seq_alloc`).
  Migration deferred per `EPIC-2B-DEBT-MIGRATE-PROCESS-LOCAL-SEQ-CALLSITES`; the
  high-level helper is the new default for any code touched after this ADR lands.
- **−** No cross-process integration test today; the architectural argument is the proof.

## Revisit-by

After Story 2B.1 lands. Confirm ClaudeAIRuntime adopts `append_with_seq_alloc` for all real-
runtime journal emissions, and decide whether to schedule the legacy-callsite migration as a
dedicated Epic 2B story or fold it into per-story refactors.

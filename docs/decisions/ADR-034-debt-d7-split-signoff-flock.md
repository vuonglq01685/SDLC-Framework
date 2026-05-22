# ADR-034: EPIC-2A-D7 Split — SIGNOFF-FLOCK Closed, WIN32-RUNS-LOCK Deferred

**Status:** Accepted (2026-05-22, Epic 2B prep — `epic-2b-prep/d7-signoff-flock`).
**Source:** Epic 2B §7.4 Pre-Story-2B.1 gate — `EPIC-2A-D7-CROSS-PLATFORM-LOCK`
(BLOCKING) was the sole open BLOCKING item gating Gate A (ADR-033 zero-open rule).
**Closes:** `EPIC-2A-D7A-SIGNOFF-FLOCK-CONCURRENCY`. **Defers:** `EPIC-2A-D7B-WIN32-RUNS-LOCK`.

## Context

`EPIC-2A-D7-CROSS-PLATFORM-LOCK` (`debt-budget.yaml`, BLOCKING) bundled two
unrelated concerns under one ticket:

1. **SIGNOFF-FLOCK-CONCURRENCY** — `signoff/records.py:_write_bytes_to_disk` does
   `tmp + fsync + replace` with no lock. Two concurrent POSIX processes calling
   `write_record` / `invalidate_record` for the same phase can both pass the
   `exists()` guard, both write the deterministic `.tmp` path, and the second
   `replace` silently wins. A genuine POSIX race.

2. **WIN32-RUNS-LOCK** — `telemetry/runs.py` and `signoff/records.py` take no
   file lock on the Windows branch (`concurrency/locks.py` is POSIX-only — it
   raises `ImportError` on Windows; `fcntl` is the only primitive exposed).

Closing the bundled ticket appeared to require a cross-platform lock primitive
(POSIX `fcntl.flock` + Windows `msvcrt.locking`). Investigation during the Epic
2B gate verification surfaced two facts that make the Windows half intractable
*and* low-value right now:

- **`ci.yml` has no Windows runner** — the matrix is `[ubuntu-latest,
  macos-latest]`. Hand-rolled `msvcrt.locking` code would be executed by no
  test, no CI job, and no developer machine — unverifiable dead code, contrary
  to the project's quality discipline.
- **The framework is POSIX-only in v1** — `journal/writer.py` raises
  `JournalError` on Windows, so `sdlc` cannot run end-to-end on Windows at all.
  The Windows lock gap is therefore unreachable in v1.

The two halves have different severity, different testability, and different
urgency. Bundling them blocks Gate A on work that is partly intractable.

## Decision

`EPIC-2A-D7` is **split** into two `debt-budget.yaml` rows:

- **`EPIC-2A-D7A-SIGNOFF-FLOCK-CONCURRENCY`** — severity **BLOCKING**, **closed**.
  `signoff/records.py` `write_record` / `invalidate_record` now hold a per-phase
  exclusive POSIX `flock` (`_signoff_write_lock`, at `<target>.lock`) across the
  exists-check / TOCTOU-read and the `tmp + replace`. Verified by two behavioural
  tests that hold the lock externally and assert the writer blocks. The
  `signoff/` module gains a **declared dependency on `concurrency/`** in
  `scripts/module_boundary_table.py` — `concurrency/` is a foundation module
  that `state/` and `journal/` (both already `signoff/` dependencies) likewise
  depend on; `concurrency.locks.file_lock` is its public flock API.

- **`EPIC-2A-D7B-WIN32-RUNS-LOCK`** — severity **LOW** (downgraded from
  BLOCKING), **open**, deferred. The Windows branches of `telemetry/runs.py` and
  `signoff/records.py` (`_signoff_write_lock` returns `contextlib.nullcontext()`
  on Windows) stay lock-free. Reactivation trigger: Windows becomes a supported
  target — which first requires a `windows-latest` CI cell *and* a
  Windows-capable `journal/writer.py`.

D7A closing leaves zero open BLOCKING items, so Gate A (ADR-033) passes.

## Alternatives Considered

- **Hand-roll `msvcrt.locking` now and close D7 as one item**: Rejected — no
  Windows runner anywhere means the code is never executed; shipping unverifiable
  Windows locking for a BLOCKING concurrency primitive is the opposite of the
  project's anti-tautology / conformance discipline.
- **Add a `windows-latest` CI cell first, then implement `msvcrt`**: Considered
  viable but rejected for this prep-item — adding a Windows runner is its own
  infrastructure story and would surface further POSIX-only failures
  (`journal/writer.py`), far exceeding the scope of closing one debt item.
  Recorded as the D7B reactivation trigger.
- **Keep D7 bundled and BLOCKING**: Rejected — it blocks Gate A on the
  intractable Windows half while the real POSIX race is a small, testable fix.
- **Re-export a lock through `state/` or `journal/` to avoid the new
  `signoff → concurrency` edge**: Rejected — indirection purely to dodge a
  boundary edge; `concurrency/` is the correct home of the lock primitive and
  the edge is architecturally sound (`telemetry/` already declares it).

## Consequences

- Gate A passes once this lands — `EPIC-2A-D7A` closed, zero open BLOCKING.
- The real POSIX `write_record` / `invalidate_record` race is fixed and tested.
- `signoff/ → concurrency/` is a new declared module-dependency edge. The
  `architecture.md` §1052 dependency table predates it; this ADR is the record
  of the addition (per the ADR-030 precedent for recording architecture deltas
  as ADRs rather than retro-editing the planning artifact).
- Windows concurrency hardening is explicitly deferred and visible as a LOW
  open item, not silently dropped.
- A debt ticket was split mid-life; the budget gains one row. Future audits and
  the debt-decay gate read `D7A` / `D7B`, not `D7`.

## Revisit-by

2027-05-15 — or when a `windows-latest` CI cell is added, at which point
`EPIC-2A-D7B-WIN32-RUNS-LOCK` becomes implementable and verifiable.

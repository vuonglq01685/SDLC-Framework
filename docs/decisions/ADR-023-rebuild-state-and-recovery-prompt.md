# ADR-023: Rebuild-State Command and Malformed-State Recovery Prompt

**Status:** Accepted (2026-05-09, [Story 1.20](../../_bmad-output/implementation-artifacts/1-20-recovery-sdlc-rebuild-state.md))

## Context

Story 1.19 introduced `read_state_or_refuse`, which raises `SchemaError` when
`state.json` contains an unrecognised `schema_version`. While this prevents silent
misreads, it leaves the operator with no recovery path when `state.json` is corrupted,
truncated, or left in an intermediate state after a failed write.

Two gaps needed closing:

1. **No recovery command** — operators had no CLI primitive to reconstruct `state.json`
   from the journal (which is append-only and therefore trustworthy).

2. **No recovery prompt** — CLI commands that read state (`sdlc scan`, `sdlc status`)
   raised a bare `StateError` without telling the operator what to do next.

Architecture Decision B4 + B5 (§348–§349) establishes that *state is a pure projection
of the journal*; this makes full-replay reconstruction a correct-by-construction
recovery strategy for any well-formed journal.

## Decision

### `sdlc.state.rebuild` — new POSIX-only module

`rebuild_state_from_journal(journal_path, state_path) -> int` is the single recovery
primitive. It:

1. Validates that both paths are absolute.
2. Raises `StateError(reason="missing_journal")` when `journal_path` does not exist —
   the caller (CLI) translates this to `ERR_NO_RECOVERY_SOURCE`.
3. Calls `project_from_journal(journal_path)` to produce a fresh `State` via full
   replay (Decision B4 — replay from journal[0]).
4. Counts entries with a second pass over the journal (`sum(1 for _ in iter_entries(…))`)
   — a deliberate double-iteration accepted as a readability trade-off for the
   disaster-recovery path (not performance-critical).
5. Writes the state atomically via `write_state_atomic_sync`.
6. Returns the entry count so callers can report progress.

The module is POSIX-only (`fcntl`-dependent). The Windows shim in
`sdlc.state.__init__` raises `NotImplementedError` with an explicit
"Recommended: WSL2" message.

### `_RECOVERY_MSG_FORMAT` — internal contract in `sdlc.state.reader`

A `Final[str]` constant named `_RECOVERY_MSG_FORMAT` is added to `sdlc.state.reader`:

```
"state.json is malformed at {state_path}. To recover: run"
" `sdlc rebuild-state` (rebuilds from journal) or"
" `sdlc migrate-vN` (if version mismatch)."
" The journal at {journal_path} is untouched."
```

This format string is the single source of truth for the recovery message surface
**inside the `sdlc.state.reader` module**. The leading underscore signals that the
constant is module-private — tests assert against substrings of the rendered message
rather than importing the constant directly. Freezing the format as a named constant
(rather than an inline f-string) keeps the wording revisable in one place; a future
story may promote the constant to `__all__` if a stable cross-module test anchor is
needed.

### `read_state_or_recover` — unified recovery wrapper in `sdlc.state.reader`

`read_state_or_recover(state_path, journal_path) -> State | None` replaces all
direct `read_state_or_refuse` calls in CLI command bodies:

- Returns `None` if `state_path` does not exist (not-initialised case).
- Calls `read_state_or_refuse` and re-raises `SchemaError` and `StateError` as
  `StateError` with `_RECOVERY_MSG_FORMAT` injected into the message and
  `remediation_primary = "sdlc rebuild-state"` in the details dict.
- **Never reads the journal.** The `journal_path` parameter is used only for message
  formatting; this invariant is tested explicitly.

### `sdlc rebuild-state` CLI command

Registered at `app.command(name="rebuild-state")` in `cli/main.py`. The handler in
`cli/rebuild_state.py`:

1. Checks `.claude/state/` directory exists (`ERR_NOT_INITIALIZED` / exit 1).
2. Checks `journal.log` exists (`ERR_NO_RECOVERY_SOURCE` / exit 2); in human mode
   emits a `"Check for backups at: …"` hint to stderr *before* calling `emit_error`.
3. Calls `rebuild_state_from_journal`; maps `JournalError` and `StateError` to
   specific error codes:
   - `reader_invariant` step → `ERR_JOURNAL_CORRUPT`
   - `project_unknown_schema` step → `ERR_JOURNAL_SCHEMA_DRIFT`
   - `missing_journal` reason → `ERR_NO_RECOVERY_SOURCE`
   - other `StateError` → `ERR_STATE_WRITE_FAILED`
4. On success emits `"state rebuilt from N journal entries"` (human) or a JSON
   envelope with `result`, `entries_replayed`, `state_path`, `journal_path` fields.

### Error code additions to `cli/output.py`

Three new codes are added to `_ERR_CODE_TO_EXIT_CODE` (all → exit 2):

| Code | Meaning |
|------|---------|
| `ERR_NO_RECOVERY_SOURCE` | No journal and no backup — operator must provide a recovery source |
| `ERR_JOURNAL_CORRUPT` | Monotonic-seq regression detected — manual intervention required |
| `ERR_JOURNAL_SCHEMA_DRIFT` | Journal contains entries with a future `schema_version` |

### Scan and status migration

`cli/scan.py` and `cli/status.py` replace their `read_state_or_refuse` /
`read_state` calls with `read_state_or_recover`, and their error codes change from
`ERR_INFRASTRUCTURE` (exit 3) to `ERR_STATE_MALFORMED` (exit 2, added in Story 1.19).
This ensures every state-reading command presents the unified recovery prompt.

### Module-boundary stance

`MODULE_DEPS` is **UNCHANGED** by this story. `state` already depends on `journal`
(via `state.projection.project_from_journal` reading `iter_entries`); `cli` already
depends on `state` (via `state.reader.read_state_or_refuse` for the schema gate).
The new `state.rebuild` module composes existing public APIs without introducing
any new boundary edges. The module-boundary linter (`tests/test_check_module_boundaries.py`)
re-runs against the post-Story-1.20 code with no new entries.

## Consequences

**Positive**

- Operators have a single, documented recovery path (`sdlc rebuild-state`) instead of
  manual JSON surgery.
- Every state-reading command surfaces the same recovery message, eliminating
  inconsistent error surfaces.
- The `_RECOVERY_MSG_FORMAT` constant is a stable test anchor; message wording can be
  revised in one place.
- `rebuild_state_from_journal` is idempotent (property-tested over 500 examples per
  invariant) and journal-untouched (unit- and integration-tested).

**Negative / trade-offs**

- Double-iteration over the journal (project + count) adds latency proportional to
  journal size. Acceptable for a disaster-recovery command; if journals grow large a
  future story can refactor `project_from_journal` to return `(State, int)` and
  collapse the two passes — the refactor signal is "rebuild latency on a 100k-entry
  journal becomes a real problem".
- POSIX-only restriction means Windows users must use WSL2 for recovery; documented
  in the shim's error message.
- `journal_path` passed to `read_state_or_recover` is formatting-only; passing the
  wrong path produces a misleading recovery message but no functional error. Callers
  (`cli/scan.py`, `cli/status.py`) `.resolve()` both `state_path` and `journal_path`
  before invocation to guarantee canonical absolute paths in the rendered message.
- The two `iter_entries` traversals (one inside `project_from_journal`, one for the
  count) are unprotected by any lock; only the final `write_state_atomic_sync`
  acquires `state.json.lock`. Under concurrent writers, the success message's
  `entries_replayed` count may not match the actually-projected state. Accepted
  because rebuild is a recovery command (disaster-recovery, not a hot loop) and
  AC2 trailing And explicitly accepts the no-flock design beyond `state.json.lock`.

**Load-bearing user-trust contract**

The "the journal at … is untouched" reassurance in the recovery prompt
(`_RECOVERY_MSG_FORMAT` in `sdlc.state.reader`) becomes a load-bearing user-trust
contract: operators read this message and decide whether to run `sdlc rebuild-state`
based on the promise that recovery is non-destructive. **Any future change that
mutates the journal during a state-malformed-read path (e.g., a side-effecting log
rotation, a journal-compaction primitive, or a "clean up partial entries" helper)
violates this contract.** The contract is enforced by `tests/integration/
test_rebuild_state_e2e.py::test_rebuild_state_does_not_mutate_journal` and
`test_rebuild_twice_produces_byte_identical_state` (subprocess-level idempotency).
Future stories that introduce journal mutation MUST either preserve this invariant
along the malformed-state-read path or amend the recovery message wording.

## Alternatives Considered

**Backup-first recovery** — restore from `.claude/state/backups/` before replaying
the journal. Deferred: backup creation is not yet implemented; the backup hint in the
`ERR_NO_RECOVERY_SOURCE` message reserves the UX slot for Story 2.x.

**Single-pass count** — count entries during projection instead of a second
`iter_entries` pass. Rejected: would require changes to `project_from_journal`'s
internal loop or a wrapper that shadows the existing API. The double-pass approach
keeps `rebuild.py` fully independent of `projection.py` internals.

**Auto-rebuild on framework startup if state.json is missing / corrupt** —
silently invoke the equivalent of `sdlc rebuild-state` whenever `read_state_or_refuse`
fails. Rejected: silent recovery hides operator intent and prevents them from making
a backup before mutating disk. The unified recovery prompt + explicit `sdlc
rebuild-state` command preserves operator agency.

**Single unified `sdlc recover` command that auto-detects rebuild vs migrate** —
a one-shot dispatcher that inspects the failure class and chooses between
`rebuild-state` and `migrate-vN`. Rejected: the two operations have very different
risk profiles (rebuild is non-destructive; migrate writes new schema), so collapsing
them into one command obscures the distinction. The recovery prompt names both
commands explicitly so the operator chooses.

**Make `rebuild_state_from_journal` idempotent via a hash check** — short-circuit
the write when the would-be-written state matches what already exists on disk.
Rejected: the atomic-write protocol already produces byte-identical output for the
same input (canonical bytes); the idempotency property test asserts this. A hash
check adds a third file-read to the recovery path with no functional benefit.

**Add a `--snapshot <seq>` parameter for partial replay** — rebuild from a
checkpoint snapshot up to seq N rather than from `journal[0]`. Deferred to v1.x:
snapshot caching is itself deferred per Decision B4. Adding the parameter now would
freeze a CLI surface for a feature that does not exist; we add it when snapshots ship.

**Add a `--from-backup <path>` parameter** — bypass the journal and restore directly
from a backup file. Deferred: `.claude/state/backups/` is the migration-backup
directory (Architecture §453), not an arbitrary user-backup repository. A
"restore from backup file" surface is a future story (concern #13 backup retention).
Operators can `cp` over `state.json` manually in v1.20.

**Make the recovery prompt configurable** — let operators override the message
format via env var or config file. Rejected: the recovery prompt is a stability
contract (see Load-bearing user-trust contract above); allowing override would
undermine the test anchors and let downstream tooling drift from the canonical
wording.

**Use a `SchemaError` subclass (`MalformedStateError`) for the wrapped error** —
emit a dedicated exception type rather than re-using `StateError` with merged
details. Rejected: the existing `StateError` already carries enough discriminator
fields (`reason`, `inner_message`, `remediation_*`) for callers to distinguish
malformation from generic state errors. A new subclass would proliferate the
exception hierarchy without behavioral benefit.

**Have `read_state_or_recover` ALSO read the journal and assert it parses cleanly** —
pre-flight the journal so the recovery prompt is more confident ("journal verified;
run `sdlc rebuild-state`"). Rejected: this would violate the "never reads the journal"
invariant that the load-bearing user-trust contract depends on. Confidence about
journal parseability belongs to `sdlc rebuild-state` itself, which fails loudly with
`ERR_JOURNAL_CORRUPT` if `iter_entries` cannot proceed.

**Fall back to backups automatically when journal is missing** — when
`ERR_NO_RECOVERY_SOURCE` would fire, instead silently restore from the most-recent
file in `.claude/state/backups/`. Rejected: no backups exist in v1.20 (the directory
is reserved). Even when backups land, automatic fallback is the wrong default — the
operator should choose between journal-replay (latest state) and backup-restore
(possibly stale) explicitly.

## Revisit-by

Re-open this ADR when any of the following conditions arise:

- **Journal corruption becomes a user-facing recovery scenario.** Triggers a
  companion `sdlc rebuild-journal` design (or a `--repair-journal` flag); the
  current ADR's invariants (journal is the source of truth; rebuild is read-only
  with respect to the journal) need explicit re-examination.
- **Backup-restore is added as a CLI surface.** `--from-backup`, an `sdlc restore`
  command, or automatic fallback would all change the recovery decision tree the
  prompt names. Update both the prompt wording and the alternatives table.
- **The recovery prompt format is changed** (e.g., to add a third recovery option,
  to localise the message, or to add a structured machine-readable hint). Bump the
  test anchors and update the load-bearing-user-trust contract paragraph.

## References

**PRD**

- §377 — recovery story for malformed state.json
- §511 — journal as source of truth (Decision B5)
- §660 — operator-facing CLI contract for disaster recovery
- §727 — error envelope shape and exit-code class
- §769 — JSON mode envelope schema for recovery commands
- §899 — NFR-DR-1 disaster-recovery coverage requirement

**Architecture**

- §139 — substrate cold-start contract
- §348 — Decision B4 (full replay from `journal[0]`)
- §349 — Decision B5 (state is journal projection)
- §453 — `.claude/state/backups/` directory layout
- §573 — POSIX-only atomic-write protocol; Windows fallback contract
- §589 — kill-between-7-and-8 recovery scenario
- §805 — `cli/rebuild_state.py` location
- §841–§846 — `state/` module layout including `state/rebuild.py`
- §1059 — `state` module surface includes `rebuild_state`
- §1135 — FR5 mapping `state/reader.py`
- §1161 — FR35 mapping `cli/rebuild_state.py + state/rebuild.py`
- §1278 — disaster-recovery surface (overall)

**Adjacent ADRs**

- ADR-013 — atomic-write protocol (the underlying primitive `rebuild.py` composes)
- ADR-014 — append-only journal (the read source for `project_from_journal`)
- ADR-015 — state-projection contract (the pure-function reducer)
- ADR-022 — major-version refusal gate (`SchemaError` is the upstream signal that
  triggers the recovery prompt)

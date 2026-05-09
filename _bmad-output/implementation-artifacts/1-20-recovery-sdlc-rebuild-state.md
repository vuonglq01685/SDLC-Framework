# Story 1.20: [Recovery] `sdlc rebuild-state` + Refuse-to-Start on Malformed State

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user whose `state.json` is lost, corrupted, or schema-incompatible,
I want `sdlc rebuild-state` to reconstruct `state.json` from the journal, and the framework to refuse-to-start with a clear recovery prompt referencing this command,
so that disaster recovery is a one-command operation, not a debugging odyssey — closing the FR5 + FR35 + NFR-DR-1 recovery slice for Epic 1's substrate (Architecture §139, §348 [Decision B4 — full replay from journal[0]], §349 [Decision B5 — state is journal projection], §453 backup directory layout, §589 kill-between-7-and-8 recovery scenario, §805 `cli/rebuild_state.py` location, §841–§846 `state/` module layout including `state/rebuild.py`, §1059 `state` module surface includes `rebuild_state`, §1135 FR5 mapping `state/reader.py`, §1161 FR35 mapping `cli/rebuild_state.py + state/rebuild.py`, §1278 disaster-recovery surface).

## Acceptance Criteria

**AC1 — `src/sdlc/state/rebuild.py` orchestrator: project-from-journal + atomic-write (epic AC block 1, FR35, Decisions B4 + B5)**

**Given** Story 1.12 has shipped `sdlc.state.projection.project_from_journal(journal_path) -> State` (cross-platform pure-function reducer over `iter_entries`) AND Story 1.10 has shipped `sdlc.state.atomic.write_state_atomic_sync(state, target) -> None` (POSIX 7-step atomic write protocol),

**When** Story 1.20 lands,

**Then**:

1. **Module skeleton.** `src/sdlc/state/rebuild.py` is created. Module docstring: `"""Rebuild state.json from journal — full replay (FR35, Decision B4 + B5, Architecture §348, §846, §1059).\n\nThis is the materialisation of the replay invariant from Story 1.12:\n  ``project_from_journal(journal[0:k]) == state_at_step_k`` for every k.\nrebuild_state_from_journal() is the user-facing recovery surface; it is\nidempotent and produces byte-equivalent state.json output to a clean run\nfrom the same journal.\n\nNot a primitive — composes ``state.projection.project_from_journal``\n(read) and ``state.atomic.write_state_atomic_sync`` (write). Both are\ncovered by their own kill-point + property tests; this module is the\nminimal seam between them.\n\nNever mutates the journal. Reads are pure; writes go through the atomic\nprotocol so a kill mid-rebuild leaves the prior state.json intact.\n"""`. First non-comment line is `from __future__ import annotations`.
2. **Top-level imports** (per Architecture §488 cold-start discipline — `state/` is below `cli/`, so the strict no-top-level rule does not apply, but minimise anyway): `from pathlib import Path`, `from typing import Final`, `from sdlc.errors import JournalError, StateError`, `from sdlc.journal import iter_entries`, `from sdlc.state.atomic import write_state_atomic_sync`, `from sdlc.state.projection import project_from_journal`. **NO** import of `cli/`, `dispatcher/`, `engine/`, `runtime/` — `state/` already forbids these per `MODULE_DEPS["state"].forbidden_from`.
3. **Public function — `rebuild_state_from_journal(journal_path: Path, state_path: Path) -> int`** is exported.
   - **Inputs.** Both paths MUST be absolute (matching `write_state_atomic_sync`'s validation contract). Relative paths raise `StateError("rebuild_state_from_journal requires absolute journal_path", details={"path": str(journal_path), "step": "validate_journal_path"})` OR `StateError("rebuild_state_from_journal requires absolute state_path", ...)` BEFORE any I/O. Validate journal_path first, then state_path.
   - **Refuse on missing journal.** If `not journal_path.exists()`: raise `StateError(f"no journal at {journal_path}; recovery requires either journal or backup", details={"path": str(journal_path), "reason": "missing_journal", "step": "validate_journal_exists"})`. Exit code 2 (StateError default). The error message MUST contain the substring `"no journal at"` AND the journal path AND the substring `"recovery requires either journal or backup"` — Story 1.20 epic AC3 mandates this verbatim text. The CLI layer (AC2) ALSO emits a hint to `.claude/state/backups/` directory; that hint is NOT part of the StateError message itself (it's the CLI's responsibility to add the backup-directory pointer to user-facing output).
   - **Replay.** Call `state = project_from_journal(journal_path)`. This may raise `JournalError(step="reader_invariant", ...)` (out-of-order seqs) or `JournalError(step="project_unknown_schema", ...)` (schema_version drift) — propagate UNCHANGED to the caller. Both indicate journal corruption; recovery is impossible without manual intervention.
   - **Count entries.** Compute `entries_replayed = sum(1 for _ in iter_entries(journal_path))` to surface a count for the success message. **WHY a SECOND iteration?** `project_from_journal` consumes the iterator internally without returning a count, and we need the count for human-readable output. The cost is one extra O(N) file scan on the recovery path (acceptable: recovery is not a hot loop). DO NOT refactor `project_from_journal` to return a tuple — that breaks Story 1.12's contract. DO NOT count via internal counter inside `_project_entries` — that requires touching `state/projection.py` and breaks its purity. Documented as a deliberate trade-off in dev notes.
   - **Atomic write.** Call `write_state_atomic_sync(state, state_path)`. This is the production sync API (no event loop). The 7-step POSIX protocol guarantees atomicity: either the whole new state.json lands or the prior state.json (if any) is preserved.
   - **Return.** Return `entries_replayed: int`. The caller (CLI layer) formats the user-facing message.
   - **Idempotency.** Calling `rebuild_state_from_journal` twice with the same journal MUST produce byte-identical state.json on disk both times (the canonical-write protocol guarantees this; the property test in AC7 asserts it).
4. **No new helpers beyond the public function.** Resist extracting `_count_entries` — it's a one-line generator expression. Resist extracting `_validate_paths` — it's three lines. Module LOC ≤ 80 (target: ~50). The function body is intentionally small; the heavy lifting lives in `state.projection` and `state.atomic`.
5. **Public API surface.** `__all__` (semantic order, with `# noqa: RUF022`) is exactly: `("rebuild_state_from_journal",)`. Re-exported from `src/sdlc/state/__init__.py` per AC4.
6. **Cross-platform stance.** `state/rebuild.py` is **POSIX-only** because it transitively depends on `write_state_atomic_sync` (POSIX-only per `state/atomic.py:11-15`). Mirror the `state/atomic.py` pattern at module top:
   ```python
   import sys
   if sys.platform == "win32":
       raise ImportError(
           "sdlc.state.rebuild is POSIX-only — depends on state.atomic"
           " (Architecture §573)"
       )
   ```
   Place this BEFORE the other imports. The Windows shim is added in `state/__init__.py` (AC4) as a `NotImplementedError` callable.
7. **Module boundary compliance.** `state.rebuild` lives inside the `state` module so MODULE_DEPS["state"] (already `frozenset({"errors", "contracts", "concurrency", "config", "journal"})` post-Story-1.12) is sufficient — no boundary changes required for AC1. Confirmed: imports of `errors`, `journal`, `state.atomic`, `state.projection` all stay within the existing dependency set.

**And** the function signature is **synchronous-only** in v1.20. The async variant (`async def rebuild_state_from_journal_async`) is NOT shipped — `cli/rebuild_state.py` (AC2) runs synchronously per the same rationale that `cli/migrate.py` runs sync (Story 1.19 AC4.6). Document in ADR-023.

**And** the function does NOT take a `monotonic_seq` "rebuild up to" parameter. Full-journal replay only in v1; partial replay (rebuild from snapshot to seq N) is a v1.x optimisation (Decision B4: "snapshot caching deferred"). Document the rejection in dev notes.

**AC2 — `src/sdlc/cli/rebuild_state.py` Typer command (epic AC blocks 1 + 3, FR35)**

**Given** Story 1.16 has shipped `cli/main.py` with the `app = typer.Typer(...)` instance + global `--no-color` / `--json` flags via `app.callback`, AND Story 1.16 has shipped `cli/output.py` exposing `emit_error`, `emit_json`, `make_console`, `is_no_color_active`, `echo`,

**When** Story 1.20 lands,

**Then**:

1. **`src/sdlc/cli/rebuild_state.py` is created.** Module docstring: `"""sdlc rebuild-state — disaster recovery from journal (FR35, NFR-DR-1, Architecture §805, §1161).\n\nReconstructs ``.claude/state/state.json`` from ``.claude/state/journal.log``\nvia ``sdlc.state.rebuild.rebuild_state_from_journal``. Refuses when the\njournal is missing (no recovery source); points the user to backups\nat ``.claude/state/backups/`` (Architecture §453). Idempotent:\nre-running on a clean rebuild produces byte-identical state.json.\n\nDoes NOT touch the journal — read-only with respect to journal.log.\n"""`. First non-comment line is `from __future__ import annotations`.
2. **Top-level imports** (per Architecture §488 cold-start discipline — `cli/` modules MUST keep top-level imports minimal): stdlib: `import logging`, `from pathlib import Path`, `from typing import Final`. Third-party: `import typer`. SDLC-imports at module top (cheap pure-Python; no pydantic-load cost): `from sdlc.cli.output import echo, emit_error, emit_json, make_console`. **DEFERRED** to function bodies (per Architecture §488): `from sdlc.state import rebuild_state_from_journal` (after AC4 re-export), `from sdlc.errors import JournalError, StateError`. Module-level constants:
   ```python
   _STATE_PATH_REL: Final[str] = ".claude/state/state.json"
   _JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
   _BACKUP_DIR_REL: Final[str] = ".claude/state/backups"
   _logger = logging.getLogger(__name__)
   ```
3. **`run_rebuild_state(ctx: typer.Context) -> None`** is the entry point invoked by `cli/main.py`'s `app.command(name="rebuild-state")` registration (AC3). Behavior, in order:
   - **Step 1 — repo root + path resolution.** Resolve `<repo_root>` via the same `_get_repo_root_or_cwd()` helper used by Stories 1.16-1.19. If `cli/_paths.py` exists from a prior story (likely from 1.16/1.17/1.18 factoring), IMPORT it: `from sdlc.cli._paths import get_repo_root_or_cwd` (deferred). Otherwise inline the 5-LOC helper. Construct `state_path = (<repo_root> / _STATE_PATH_REL).resolve()`, `journal_path = (<repo_root> / _JOURNAL_PATH_REL).resolve()`, `backup_dir = (<repo_root> / _BACKUP_DIR_REL).resolve()`.
   - **Step 2 — `.claude/state/` parent directory check.** If `not state_path.parent.exists()`: `emit_error("ERR_NOT_INITIALIZED", "sdlc: project not initialized at <repo_root>; run `sdlc init` first", ctx=ctx, details={"path": str(state_path.parent)})` and exit 1. This catches the case where a user runs `rebuild-state` in a non-SDLC directory; without it the journal-missing branch (Step 4) would fire with a less-helpful message. Mirror Stories 1.17-1.18's not-initialized refusal pattern verbatim.
   - **Step 3 — refuse if both state.json and journal.log missing.** If `not journal_path.exists() AND not state_path.exists()`: this is the classic "I deleted everything" disaster scenario (epic AC3). Emit:
     ```text
     ERR_NO_RECOVERY_SOURCE: no journal at <journal_path>; recovery requires either journal or backup.
     Check for backups at: <backup_dir>
     ```
     Use `emit_error("ERR_NO_RECOVERY_SOURCE", "no journal at {journal_path}; recovery requires either journal or backup", ctx=ctx, details={"journal_path": str(journal_path), "state_path": str(state_path), "backup_dir": str(backup_dir), "reason": "no_recovery_source"})`. Exit code 2. The hint `Check for backups at: <backup_dir>` is appended to stderr in human mode via `emit_error`'s details rendering OR a follow-up `_console.stderr.print(...)` call (the exact mechanism depends on Story 1.16/1.17's `emit_error` body — match whatever convention exists).
   - **Step 4 — refuse if only journal missing.** If `not journal_path.exists()` (but state.json may exist): `rebuild_state_from_journal` will refuse with `StateError(reason="missing_journal")`. Either pre-empt with the same error envelope or let it propagate and catch in Step 6's handler. Pre-empt for cleaner UX: `emit_error("ERR_NO_RECOVERY_SOURCE", ...)` exit 2; same wording as Step 3 (the hint about backups still applies — the user may want to restore state.json from a backup if no journal exists).
   - **Step 5 — invoke rebuild.** Call `entries_replayed = rebuild_state_from_journal(journal_path, state_path)`. Catch:
     - `StateError` with `details["reason"] == "missing_journal"`: should not fire here (Step 4 pre-empted) but defensively map to `ERR_NO_RECOVERY_SOURCE` exit 2.
     - `StateError` with other reasons (e.g., write failure during atomic write): map to `ERR_STATE_WRITE_FAILED` exit 2.
     - `JournalError` with `details["step"] == "reader_invariant"` (seq regression): map to `ERR_JOURNAL_CORRUPT` exit 2 with message `"journal corruption: monotonic_seq regression at line N (prev_seq={p}, next_seq={n}); manual intervention required"`. The journal is irrecoverable without surgery; the message names the offending line.
     - `JournalError` with `details["step"] == "project_unknown_schema"`: map to `ERR_JOURNAL_SCHEMA_DRIFT` exit 2 with message `"journal contains entries with schema_version={N}; this build expects schema_version=1; run `sdlc migrate-v{N}` after recovering or rebuild from a journal that pre-dates the schema bump"`.
     - Other `JournalError`: map to `ERR_INFRASTRUCTURE` exit 3 (I/O or unexpected reader error).
     - Document the mapping inline as a constant dict at module top:
       ```python
       _ERROR_DISPATCH: Final[dict[tuple[str, str], str]] = {
           ("StateError", "missing_journal"): "ERR_NO_RECOVERY_SOURCE",
           ("StateError", "*"): "ERR_STATE_WRITE_FAILED",
           ("JournalError", "reader_invariant"): "ERR_JOURNAL_CORRUPT",
           ("JournalError", "project_unknown_schema"): "ERR_JOURNAL_SCHEMA_DRIFT",
           ("JournalError", "*"): "ERR_INFRASTRUCTURE",
       }
       ```
       (Pseudo — the actual implementation may use a small if-tree if matching star patterns adds friction; the table is documentation.)
   - **Step 6 — success output.** Human mode: `echo(make_console(ctx), f"state rebuilt from {entries_replayed} journal entries")` exit 0. JSON mode: `emit_json({"command": "rebuild-state", "result": "success", "entries_replayed": entries_replayed, "state_path": str(state_path), "journal_path": str(journal_path)})` exit 0.
4. **NO journal entry is appended for the rebuild operation.** Rebuilding state.json is a meta-operation OUTSIDE the journal's invariant (parallel to Story 1.19 AC3.4 for migrations). The journal records state mutations within a schema version; it does NOT record schema-bump or rebuild events. Document in ADR-023 + dev notes.
5. **NO `--dry-run` flag in v1.20.** A future story may add `sdlc rebuild-state --dry-run` to print the would-be state.json without writing — useful for forensics. v1.20 is recovery-only; users can always `cp state.json state.json.bak` before running. Document the rejection in dev notes.
6. **NO `--from-backup <path>` flag in v1.20.** Architecture §453's `.claude/state/backups/` directory holds migration backups, not arbitrary user backups. A "restore from backup file" command is a future story (Concern #13 backup retention). v1.20 is journal-only. Document.
7. **`cli/rebuild_state.py` LOC ≤ 200** (target: ~120). Functions: `_get_repo_root_or_cwd` (or import), `_resolve_paths`, `_check_initialized_or_refuse`, `_check_recovery_source_or_refuse`, `_dispatch_error`, `_emit_success`, `run_rebuild_state` (orchestrator). Each ≤ 40 LOC. Mypy strict + ruff format MUST pass.
8. **NO `print()` calls.** All user-facing output via `echo` / `emit_json` / `emit_error`. All internal logs via `_logger.{info,warning,error}`.

**And** every error path supports `--json` mode through the standard `emit_error` envelope. Tests cover both human and JSON modes for each error class (AC7).

**And** the rebuild command does NOT acquire any locks beyond what `write_state_atomic_sync` (Story 1.10) acquires internally. The `state.json.lock` flock is acquired ONCE during the atomic write — no concurrent rebuild execution is supported (a second `sdlc rebuild-state` invocation while the first is mid-write will block on flock, which is the correct behaviour — only one rebuild may proceed at a time).

**AC3 — `cli/main.py` registers `rebuild-state` command (epic AC block 1)**

**Given** Story 1.16 ships `cli/main.py` with the `app = typer.Typer(...)` instance + the established subcommand-registration pattern (`@app.command(name="...")` or `app.command(...)(callable)`),

**When** Story 1.20 lands,

**Then**:

1. **Static registration.** `cli/main.py` is EXTENDED (NOT rewritten) to add the `rebuild-state` subcommand registration. Place AFTER existing subcommand registrations from Stories 1.16-1.19 (init, scan, status, trace, replay, logs, migrate-v\*) and BEFORE the `_register_migrate_commands(app)` call from Story 1.19 (so the static command lands first; the dynamic migrate-vN registrations may come after — order does not affect Typer's behaviour but improves readability).
2. **Implementation pattern.** Mirror Story 1.18's pattern for `trace`/`replay`/`logs`:
   ```python
   @app.command(name="rebuild-state")
   def _rebuild_state_cmd(ctx: typer.Context) -> None:
       """Rebuild state.json from the journal (FR35)."""
       from sdlc.cli.rebuild_state import run_rebuild_state  # deferred per Architecture §488
       run_rebuild_state(ctx=ctx)
   ```
   The `name="rebuild-state"` (with the dash) MUST be exact — PRD §511 commits to this user-facing surface.
3. **Help-text discoverability.** Running `sdlc --help` after this story lists `rebuild-state` as a subcommand alongside `init`, `scan`, `status`, `trace`, `replay`, `logs`. The docstring `"""Rebuild state.json from the journal (FR35)."""` becomes the short help text.
4. **Cold-start budget.** The deferred-import pattern keeps cold-start under the < 200 ms budget per Architecture §488. Verify: `python -c "import time; t=time.perf_counter(); import sdlc.cli.main; print((time.perf_counter()-t)*1000, 'ms')"` MUST stay under 200 ms in CI. Story 1.20 adds zero top-level state imports to `cli/main.py` — only the `@app.command` decorator wraps the command body, which is itself a deferred-import shim.
5. **Boundary linter compliance.** `cli/main.py`'s deferred import of `from sdlc.state import rebuild_state_from_journal` requires `MODULE_DEPS["cli"]` to include `"state"` — already present per Story 1.16's widening. No `MODULE_DEPS` edit required.

**And** the `_rebuild_state_cmd` registration is COVERED by a unit test in `tests/unit/cli/test_main.py` (extends the existing file from Stories 1.16-1.18-1.19) that asserts `rebuild-state` appears in `sdlc --help` output via Typer's `CliRunner`.

**AC4 — `state/__init__.py` re-export + Windows shim (epic AC blocks all)**

**Given** the existing `src/sdlc/state/__init__.py` follows the pattern of conditional re-export by `sys.platform != "win32"` (lines 9-30) AND Story 1.19 will append `read_state_or_refuse`, `read_state_raw`, `write_state_raw_atomic_sync`, `CURRENT_SCHEMA_VERSION` to `__all__`,

**When** Story 1.20 lands,

**Then**:

1. **Add re-export.** Inside the `if sys.platform != "win32":` branch, append `from sdlc.state.rebuild import rebuild_state_from_journal` to the existing import block.
2. **Add Windows shim.** Inside the `else:` branch, append the parallel `NotImplementedError` shim:
   ```python
   def rebuild_state_from_journal(*_: object, **__: object) -> int:
       raise NotImplementedError(
           "rebuild_state_from_journal is POSIX-only — see Architecture §573"
       )
   ```
   The return type is `int` to match the public function signature (Windows shim must satisfy mypy's strict mode given `__all__` exposure).
3. **Update `__all__`.** Append `"rebuild_state_from_journal"` to the tuple. Final order (semantic, with `# noqa: RUF022`) — append at the end of the existing tuple AFTER Story 1.19's additions:
   ```python
   __all__ = (  # noqa: RUF022
       "State",
       "write_state_atomic",
       "write_state_atomic_sync",
       "write_state_raw_atomic_sync",         # Story 1.19
       "read_state",
       "read_state_or_refuse",                # Story 1.19
       "read_state_raw",                      # Story 1.19
       "project_from_journal",
       "rebuild_state_from_journal",          # Story 1.20
       "CURRENT_SCHEMA_VERSION",              # Story 1.19
   )
   ```
   **GATING:** if Story 1.19 has NOT shipped at story-implement time (sprint-status `1-19: ready-for-dev` per snapshot 2026-05-09), the four Story-1.19 entries (`write_state_raw_atomic_sync`, `read_state_or_refuse`, `read_state_raw`, `CURRENT_SCHEMA_VERSION`) will be ABSENT from `__all__`. Story 1.20 MUST coordinate: do NOT delete Story 1.19's pending entries from the merge-base; do NOT introduce them speculatively. Add ONLY `rebuild_state_from_journal` and the Windows shim. The eventual merge of 1.19 + 1.20 produces the union.
4. **Smoke verification.** `uv run python -c "from sdlc.state import rebuild_state_from_journal; print(rebuild_state_from_journal)"` MUST print a function reference, not raise on POSIX.

**And** mypy --strict on `src/sdlc/state/` MUST pass. The Windows shim's `int` return annotation prevents `[no-any-return]` from firing on the production path.

**AC5 — Refuse-to-start gate: `read_state_or_recover` + canonical recovery prompt (epic AC block 2, FR5, NFR-DR-1)**

**Given** Story 1.19 ships `state/reader.py` with `read_state_or_refuse(target: Path) -> State | None` (raises `SchemaError` on schema_version mismatch with the specific message `"schema_version mismatch: state is v{N}, framework expects v{M}; run \`sdlc migrate-v{M}\`"`, raises `StateError` with `details["reason"] in {"json", "io", "missing_schema_version", "schema"}` on other malformations, returns `None` if file missing),

**When** Story 1.20 lands,

**Then**:

1. **EXTEND `state/reader.py`** (Story 1.19 owns this file). Story 1.20 ADDS a new public function `read_state_or_recover(state_path: Path, journal_path: Path) -> State | None` that wraps `read_state_or_refuse` and converts errors to a unified recovery prompt. The function is the canonical entry point for any CLI subcommand that reads state.json.
2. **Define module-level format constant** alongside Story 1.19's `_REFUSAL_MSG_FORMAT`:
   ```python
   _RECOVERY_MSG_FORMAT: Final[str] = (
       "state.json is malformed at {state_path}. To recover: run"
       " `sdlc rebuild-state` (rebuilds from journal) or"
       " `sdlc migrate-vN` (if version mismatch)."
       " The journal at {journal_path} is untouched."
   )
   ```
   The format string MUST contain (substring-asserted in tests):
   - the literal `"state.json is malformed at "`
   - the literal `"sdlc rebuild-state"`
   - the literal `"sdlc migrate-vN"` (the LITERAL `"vN"`, not a template placeholder — this is the user-facing recovery hint when the version is unknown OR when the malformation is not a version mismatch)
   - the literal `"The journal at "` AND `" is untouched."`
3. **Implement `read_state_or_recover(state_path: Path, journal_path: Path) -> State | None`**:
   - Returns `None` if `state_path` does not exist (delegates to `read_state_or_refuse` semantics; missing state is NOT a malformation — it's a different error surface, handled by callers as `ERR_NOT_INITIALIZED`).
   - Calls `read_state_or_refuse(state_path)`. On success returns the State.
   - On `SchemaError` (schema_version mismatch from Story 1.19): re-raises a NEW `StateError` whose message is `_RECOVERY_MSG_FORMAT.format(state_path=state_path, journal_path=journal_path)` AND whose `details` MERGES Story 1.19's details with the Story 1.20 wrapper:
     ```python
     details = {
         **story_1_19_err.details,
         "state_path": str(state_path),
         "journal_path": str(journal_path),
         "reason": "schema_version_mismatch",
         "inner_message": story_1_19_err.message,  # preserves the migrate-vN guidance
         "remediation_primary": "sdlc rebuild-state",
         "remediation_alternative": story_1_19_err.details.get("remediation"),
     }
     ```
     The `chain` from `__cause__` is preserved (use `raise StateError(...) from err`). Note: Story 1.19's `SchemaError` becomes a `StateError` here — the gate UNIFIES the user-facing error class so callers handle one exception type. Both inherit from `SdlcError` so existing `except SdlcError` catches still work.
   - On `StateError` from Story 1.19 (`details["reason"] in {"json", "io", "missing_schema_version", "schema", "not_object"}`): re-raises a NEW `StateError` whose message is `_RECOVERY_MSG_FORMAT.format(state_path=state_path, journal_path=journal_path)` AND whose `details` MERGES the inner details with the wrapper:
     ```python
     details = {
         **story_1_19_err.details,
         "state_path": str(state_path),
         "journal_path": str(journal_path),
         "inner_message": story_1_19_err.message,
         "remediation_primary": "sdlc rebuild-state",
         "remediation_alternative": "sdlc migrate-vN",
     }
     ```
     Preserve `__cause__` chain via `raise from`.
   - Other exception types (e.g., the current implementation does not raise other types, but a future Story 1.19 patch might): allow to propagate UNCHANGED. Document in the function docstring as a known passthrough.
4. **Public surface update.** `state/reader.py`'s `__all__` (managed by Story 1.19 per AC2.2) gains `"read_state_or_recover"` appended at the end. Story 1.20 MUST coordinate with Story 1.19's `__all__` definition. If Story 1.19 has not landed at merge time, the Story 1.20 patch lands `read_state_or_recover` and `_RECOVERY_MSG_FORMAT` ALONGSIDE Story 1.19's symbols (the patch encompasses the entire module). The semantic-order tuple becomes:
   ```python
   __all__ = (  # noqa: RUF022
       "CURRENT_SCHEMA_VERSION",
       "read_state_or_refuse",
       "read_state_or_recover",  # Story 1.20
       "read_state_raw",
   )
   ```
5. **`state/__init__.py` re-export** of `read_state_or_recover` (alongside Story 1.19's `read_state_or_refuse` re-export). Inside the `if sys.platform != "win32":` branch, append:
   ```python
   from sdlc.state.reader import read_state_or_recover
   ```
   Inside the `else:` branch:
   ```python
   def read_state_or_recover(*_: object, **__: object) -> None:
       raise NotImplementedError("read_state_or_recover is POSIX-only — see Architecture §573")
   ```
   Update `state/__init__.py:__all__` (already updated by Story 1.19 + AC4 above) to include `"read_state_or_recover"`.
6. **No mutation of the journal.** `read_state_or_recover` is a PURE READ. It does NOT call `iter_entries` on the journal_path; it does NOT touch the journal file at all. The `journal_path` parameter is purely for message formatting — to tell the user WHERE the journal is and that it's "untouched". This is an intentional design choice per the epic AC: the message reassures the user that recovery is safe because the journal (the source of truth per Decision B5) is intact.
7. **`state/reader.py` cross-platform stance.** Per Story 1.19 AC2.4 closing note, `state/reader.py` is **cross-platform** (no `fcntl`, no flock — pure read). Story 1.20's `read_state_or_recover` inherits this property: no platform-specific APIs.

**And** the function's docstring explicitly states: "Use this function from any CLI subcommand that reads state.json. It composes Story 1.19's `read_state_or_refuse` schema gate with the Story 1.20 recovery-prompt formatter."

**And** the "(if version mismatch)" clause in the recovery prompt is a parenthetical guidance, not a conditional. The same message format is used for ALL malformations — whether the user sees a version mismatch or a corrupt JSON file, they see the same recovery prompt. The `details["inner_message"]` field preserves the specific Story 1.19 wording (`"schema_version mismatch: state is v2, framework expects v1; run \`sdlc migrate-v1\`"`) for forensic / programmatic consumers (JSON mode renders this in the error envelope).

**AC6 — Wire the gate into existing `cli/` subcommands (epic AC block 2)**

**Given** Stories 1.16-1.19 ship CLI subcommands (`init`, `scan`, `status`, `trace`, `replay`, `logs`, `migrate-vN`) that read state.json via `read_state_or_refuse` (Story 1.19) OR via the legacy `read_state` (Story 1.10, redirected by Story 1.19 to `read_state_or_refuse`),

**When** Story 1.20 lands,

**Then**:

1. **Update every CLI subcommand that reads state.json** to call `read_state_or_recover(state_path, journal_path)` instead of `read_state_or_refuse(state_path)`. The list of touched files (snapshot at story-implement time; verify by `grep -rln 'read_state_or_refuse\|read_state(' src/sdlc/cli/`):
   - `src/sdlc/cli/scan.py` (Story 1.17 — if shipped)
   - `src/sdlc/cli/status.py` (Story 1.17 — if shipped)
   - `src/sdlc/cli/trace.py` (Story 1.18 — if shipped)
   - `src/sdlc/cli/replay.py` (Story 1.18 — if shipped)
   - `src/sdlc/cli/logs.py` (Story 1.18 — if shipped)
   - `src/sdlc/cli/migrate.py` (Story 1.19 — if shipped). Note: `migrate.py` uses `read_state_raw` (gate-bypass) for the migration-payload read, but if it ALSO calls `read_state_or_refuse` for any other purpose, that call must be updated. Story 1.19's AC3.3 Step 3 uses `read_state_raw` exclusively — so likely no change here.
2. **`cli/init.py` is the EXCEPTION.** The init command CREATES `state.json`; calling `read_state_or_recover` on a missing file would just return `None` (correct behavior). However, init does NOT need the recovery prompt — it's about to create the file. Document: `cli/init.py` keeps its existing read pattern (or no read at all); Story 1.20 does NOT touch `cli/init.py`.
3. **`cli/rebuild_state.py` is the OTHER EXCEPTION** (this story's own command). It does NOT call `read_state_or_recover` on state.json — its job is to REBUILD state.json from the journal. It reads journal.log directly (via `iter_entries` inside `state.rebuild`).
4. **Migration discipline for the gate change.** For each updated file:
   - Replace `from sdlc.state import read_state_or_refuse` with `from sdlc.state import read_state_or_recover`.
   - Replace the call `state = read_state_or_refuse(state_path)` with `state = read_state_or_recover(state_path, journal_path)`.
   - The caller MUST construct `journal_path = (<repo_root> / ".claude/state/journal.log").resolve()` before the call. In `cli/trace.py` / `cli/replay.py` / `cli/logs.py` / `cli/status.py` (Stories 1.17-1.18), the journal_path is ALREADY computed (those commands read the journal directly). Reuse the existing variable.
   - In `cli/scan.py` (Story 1.17, if it reads state.json), add the journal_path computation if absent.
5. **Catch the new error envelope.** Any `try/except StateError` block in the touched files MUST handle the wrapped error correctly. Since `read_state_or_recover` raises `StateError` (NOT `SchemaError`) for schema_version mismatch, callers that previously did `except SchemaError` for the v1.19 schema-mismatch case MUST now catch `StateError` (or `SdlcError` — the parent class). Update:
   - `cli/migrate.py` (if it had a `SchemaError` catch for the schema-mismatch case) — but per Story 1.19 AC3.3, `migrate.py` uses `read_state_raw` which bypasses the gate; this is likely a no-op.
   - All other CLI files: change `except StateError as err:` to handle the new `details["state_path"]` / `details["journal_path"]` keys when emitting via `emit_error`.
6. **Compatibility shim window.** Story 1.20 MUST land within the same merge window as Story 1.19 (or after). If Stories 1.16-1.18 land FIRST and Story 1.20 lands WITHOUT Story 1.19, the gate function (`read_state_or_recover`) will not exist — the dev MUST coordinate. The recommended sequence: **1.16 → 1.17 → 1.18 → 1.19 → 1.20**. If sequence is broken, the dev annotates the deferred-work file with the gating issue.
7. **No CLI subcommand may bypass the gate** (except `init` and `rebuild-state` per AC6.2/3). A future story adding a new CLI subcommand that reads state.json MUST call `read_state_or_recover`. This is documented as a project convention in the docstring of `state/reader.py:read_state_or_recover` AND in ADR-023.

**And** the test `tests/unit/cli/test_main.py` is EXTENDED with a discovery test: for every Typer command registered on `app`, assert that the command's body either (a) does NOT call `read_state` / `read_state_or_refuse` OR (b) is in the allow-list `{init, rebuild-state}`. Implementation: scan command callables via `app.registered_commands` and assert via AST parsing of the source. **OPTIONAL** — if static-analysis cost is high, defer to a runtime smoke test that invokes each command with a malformed state.json and asserts the recovery prompt appears (AC7.4 covers this).

**AC7 — Tests prove rebuild + refusal + idempotency end-to-end (epic AC blocks all)**

**Given** the test pyramid established by Stories 1.4-1.19,

**When** Story 1.20 lands,

**Then** the test suite contains:

1. **Unit tests** at `tests/unit/state/test_rebuild.py` (NEW; with `pytestmark = [pytest.mark.unit, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — depends on state.atomic")]`):
   - `test_rebuild_state_from_journal_rejects_relative_journal_path(tmp_path)`: pass a relative `Path("journal.log")` as `journal_path`; assert `StateError` raised; assert `err.details["step"] == "validate_journal_path"`.
   - `test_rebuild_state_from_journal_rejects_relative_state_path(tmp_path)`: pass an absolute journal_path AND a relative state_path; assert `StateError` raised; assert `err.details["step"] == "validate_state_path"`.
   - `test_rebuild_state_from_journal_refuses_when_journal_missing(tmp_path)`: assert `StateError` raised with `details["reason"] == "missing_journal"`; assert `err.message` contains `"no journal at"` AND `str(journal_path)` AND `"recovery requires either journal or backup"`.
   - `test_rebuild_state_from_empty_journal_writes_default_state(tmp_path)`: create an empty journal file (touch); call `rebuild_state_from_journal(journal_path, state_path)`; assert returns `0`; assert state.json exists with `{"schema_version": 1, "next_monotonic_seq": 0, "epics": {}}` (canonical bytes).
   - `test_rebuild_state_from_journal_with_3_entries_writes_correct_state(tmp_path)`: write 3 valid `state_mutation` entries to journal via `append_sync` (e.g., epic-1 phase=1, epic-1 phase=2, epic-2 phase=1); call rebuild; assert returns `3`; assert state.json contains the projected epics dict.
   - `test_rebuild_state_byte_equivalent_to_full_replay(tmp_path)`: write N entries via `append_sync`; call `state_a = project_from_journal(journal_path)` + `write_state_atomic_sync(state_a, alt_path_a)`; call `rebuild_state_from_journal(journal_path, alt_path_b)`; assert `alt_path_a.read_bytes() == alt_path_b.read_bytes()`. This is the AC1 byte-equivalence proof.
   - `test_rebuild_state_idempotent(tmp_path)`: write entries; call `rebuild_state_from_journal` twice; assert state.json bytes UNCHANGED between runs.
   - `test_rebuild_state_propagates_journal_error_on_seq_regression(tmp_path)`: write a journal whose 2nd entry has seq < 1st entry's seq (use `_canonicalize_entry` + raw `Path.write_bytes` to bypass the writer's regression check); call rebuild; assert `JournalError` raised with `details["step"] == "reader_invariant"`.
   - `test_rebuild_state_propagates_journal_error_on_schema_drift(tmp_path)`: write a journal whose entry has schema_version=2 (use `JournalEntry.model_construct` to bypass `Literal[1]` then manually serialize); call rebuild; assert `JournalError` raised with `details["step"] == "project_unknown_schema"`.
   - `test_rebuild_state_overwrites_existing_state_json(tmp_path)`: write a stale state.json with `schema_version:1, next_monotonic_seq:99, epics:{}`; write a journal with 1 entry (seq=0); call rebuild; assert state.json now reflects the journal (next_monotonic_seq=1, epics from the entry).
   - `test_rebuild_state_kill_safety_via_atomic_write(tmp_path)`: invoke rebuild; assert `state.json.tmp` does NOT exist post-call; assert `state.json.lock` is RELEASED (no leftover file). This is a smoke test; the chaos test in AC7.5 covers the kill-point matrix.
2. **Property tests** at `tests/property/test_rebuild_invariant.py` (NEW; `pytestmark = [pytest.mark.property, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")]`):
   - `test_rebuild_byte_equivalent_to_full_replay_for_arbitrary_journal()`: hypothesis strategy generates a list of valid `JournalEntry` records with strictly-increasing `monotonic_seq`; write them to a journal via `append_sync`; call `rebuild_state_from_journal(journal_path, state_path_a)`; call `project_from_journal(journal_path)` + `write_state_atomic_sync(s, state_path_b)`; assert `state_path_a.read_bytes() == state_path_b.read_bytes()`. Generation strategy reuses Story 1.12's `monotonic_sequence_strategy` (`tests/property/test_replay_invariant.py:monotonic_sequence_strategy`) — **import** it rather than duplicate.
   - `test_rebuild_idempotent_for_arbitrary_journal()`: hypothesis strategy generates an arbitrary journal; call rebuild twice; assert byte-equivalence between runs.
   - `test_rebuild_returns_correct_entry_count()`: hypothesis strategy generates a journal with N entries; call rebuild; assert returns N.
3. **Unit tests** at `tests/unit/state/test_reader.py` (EXTEND Story 1.19's file):
   - `test_read_state_or_recover_returns_none_when_missing(tmp_path)`: assert `read_state_or_recover(tmp_path/"nope.json", tmp_path/"journal.log") is None`.
   - `test_read_state_or_recover_passes_v1_state(tmp_path)`: write a valid v1 state.json via `write_state_atomic_sync`; assert returns a `State` instance.
   - `test_read_state_or_recover_wraps_schema_version_mismatch_with_recovery_prompt(tmp_path)`: write `{"schema_version":2, "next_monotonic_seq":0, "epics":{}}` to state.json; call `read_state_or_recover(state_path, journal_path)`; assert `StateError` raised; assert message contains `"state.json is malformed at "` AND `str(state_path)` AND `"sdlc rebuild-state"` AND `"sdlc migrate-vN"` AND `str(journal_path)` AND `"is untouched"`; assert `err.details["reason"] == "schema_version_mismatch"`; assert `err.details["inner_message"]` contains `"schema_version mismatch"` AND `"sdlc migrate-v1"` (the Story 1.19 specific wording is preserved); assert `err.__cause__` is the original SchemaError.
   - `test_read_state_or_recover_wraps_invalid_json_with_recovery_prompt(tmp_path)`: write `not-json` to state.json; call `read_state_or_recover`; assert `StateError`; assert message contains the recovery prompt tokens; assert `err.details["reason"] == "json"` (preserved from Story 1.19).
   - `test_read_state_or_recover_wraps_missing_schema_version(tmp_path)`: write `{"foo":"bar"}` (no schema_version); call `read_state_or_recover`; assert `StateError`; assert message contains the recovery prompt tokens; assert `err.details["reason"] == "missing_schema_version"`.
   - `test_read_state_or_recover_wraps_pydantic_validation_error(tmp_path)`: write `{"schema_version":1, "next_monotonic_seq":-1, "epics":{}}` (negative seq violates `Field(ge=0)`); call `read_state_or_recover`; assert `StateError`; assert message contains the recovery prompt tokens; assert `err.details["reason"] == "schema"`.
   - `test_read_state_or_recover_message_names_state_path_and_journal_path(tmp_path)`: write malformed state.json; call with explicit paths; assert message contains BOTH paths verbatim (substring assertion).
   - `test_read_state_or_recover_does_not_read_journal(tmp_path)`: write a malformed state.json AND a journal that would raise `JournalError` if read (e.g., out-of-order seqs); call `read_state_or_recover`; assert ONLY the state.json error surfaces (not the journal error) — proves the journal is not touched on the read path.
4. **Unit tests** at `tests/unit/cli/test_rebuild_state.py` (NEW; `pytestmark = [pytest.mark.unit, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — atomic state write")]`):
   - `test_rebuild_state_refuses_when_state_dir_missing(tmp_path)`: invoke `run_rebuild_state(ctx)` against a `tmp_path` with no `.claude/` dir; assert exit 1; stderr contains `"not initialized"` AND `"sdlc init"`.
   - `test_rebuild_state_refuses_when_journal_and_state_both_missing(tmp_path)`: bootstrap `.claude/state/` dir but leave both files absent; invoke; assert exit 2; stderr contains `"no journal at"` AND `"recovery requires either journal or backup"`; stderr ALSO contains the backup-directory hint `Check for backups at:` AND `str(backup_dir)`.
   - `test_rebuild_state_refuses_when_only_journal_missing(tmp_path)`: bootstrap with state.json present BUT no journal.log; invoke; assert exit 2; stderr contains the same `"no journal at"` recovery prompt.
   - `test_rebuild_state_succeeds_with_intact_journal(tmp_path)`: bootstrap with state.json AND a journal of 3 entries; delete state.json; invoke; assert exit 0; stdout contains `"state rebuilt from 3 journal entries"`; assert state.json now exists with the projected content.
   - `test_rebuild_state_succeeds_with_empty_journal(tmp_path)`: bootstrap with empty journal (just `touch`); delete state.json; invoke; assert exit 0; stdout contains `"state rebuilt from 0 journal entries"`; state.json is the default `{"schema_version":1, "next_monotonic_seq":0, "epics":{}}` (canonical bytes).
   - `test_rebuild_state_succeeds_with_state_already_present(tmp_path)`: bootstrap with state.json AND journal; do NOT delete state.json; invoke; assert exit 0; assert state.json is OVERWRITTEN with the rebuilt content (byte-equal to `project_from_journal` output).
   - `test_rebuild_state_emits_journal_corrupt_on_seq_regression(tmp_path)`: bootstrap with a manually-corrupted journal (seq regression); invoke; assert exit 2; stderr contains `"ERR_JOURNAL_CORRUPT"` AND `"monotonic_seq regression"`.
   - `test_rebuild_state_emits_schema_drift_on_unknown_version(tmp_path)`: bootstrap with a journal containing schema_version=2 entry (handcrafted); invoke; assert exit 2; stderr contains `"ERR_JOURNAL_SCHEMA_DRIFT"`.
   - `test_rebuild_state_json_mode_success_envelope(tmp_path)`: bootstrap with valid setup; invoke via CliRunner with `["--json", "rebuild-state"]`; assert `json.loads(stdout)` has keys `{"command", "result", "entries_replayed", "state_path", "journal_path"}`; assert `result == "success"`; assert `entries_replayed` is an int.
   - `test_rebuild_state_json_mode_no_recovery_source_envelope(tmp_path)`: bootstrap missing both files; invoke `["--json", "rebuild-state"]`; assert `json.loads(stderr)["error"]["code"] == "ERR_NO_RECOVERY_SOURCE"`; assert `details` includes `journal_path`, `state_path`, `backup_dir`.
   - `test_rebuild_state_idempotent(tmp_path)`: bootstrap with valid journal; invoke twice; assert state.json bytes UNCHANGED between runs; assert exit 0 both times.
   - `test_rebuild_state_does_not_mutate_journal(tmp_path)`: bootstrap; record `journal.log` bytes pre-rebuild; invoke; assert post-rebuild journal bytes EQUAL pre-rebuild bytes (the journal is untouched per the recovery contract).
5. **Chaos test EXTENSION** at `tests/chaos/test_atomic_write_kill_points.py` (extend Story 1.10's chaos suite, OPTIONAL but RECOMMENDED — coverage of the rebuild path through the kill-point matrix):
   - `test_rebuild_state_kill_at_each_kill_point(kill_point)`: parametrize over the 10 KillPoints from `tests/chaos/kill_points.py`; pre-populate a journal with 5 entries; invoke `rebuild_state_from_journal` in a subprocess that triggers a kill at the parametrized point; post-recovery, assert state.json is EITHER the prior state (if kill before rename) OR the new rebuilt state (if kill after rename); never partial. Mirror Story 1.10's chaos pattern. **GATING:** if the chaos harness is over-engineered for v1, mark this test as `@pytest.mark.skip(reason="chaos coverage of rebuild deferred to test-hardening story")` and document in deferred-work.md.
6. **Unit tests** at `tests/unit/cli/test_main.py` (EXTEND existing file from Stories 1.16-1.19):
   - `test_main_app_rebuild_state_command_is_registered()`: invoke `["--help"]`; assert `"rebuild-state"` appears in the subcommand list.
   - `test_main_app_rebuild_state_short_help_text()`: invoke `["--help"]`; assert the help text near `rebuild-state` mentions `"FR35"` OR `"rebuild"` (loose substring match — exact wording is owned by the docstring).
7. **Integration test** at `tests/integration/test_rebuild_state_e2e.py` (NEW; `pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")]`):
   - `test_full_rebuild_lifecycle(tmp_path)`: in tmp_path: `subprocess.run(["uv", "run", "sdlc", "init"])`; manually inject N journal entries via in-process `append_sync`; delete `.claude/state/state.json`; run `subprocess.run(["uv", "run", "sdlc", "rebuild-state"])`; assert exit 0; assert state.json exists with the projected content.
   - `test_refusal_message_on_malformed_state_for_status_command(tmp_path)`: bootstrap; manually overwrite state.json with `not-json`; run `subprocess.run(["uv", "run", "sdlc", "status"])` (Story 1.17's command); assert exit 2; stderr contains `"state.json is malformed at"` AND `"sdlc rebuild-state"` AND `"sdlc migrate-vN"` AND `"is untouched"`. **GATING:** if Story 1.17 (`sdlc status`) hasn't shipped, swap with whichever subcommand HAS shipped (`sdlc scan`, `sdlc trace`, etc.). Document.
   - `test_refusal_message_on_schema_mismatch_for_status_command(tmp_path)`: bootstrap; manually overwrite state.json with `{"schema_version":2, "next_monotonic_seq":0, "epics":{}}`; run `sdlc status`; assert exit 2; stderr contains BOTH the recovery prompt tokens AND the inner Story 1.19 message `"schema_version mismatch: state is v2, framework expects v1"` (the inner message is rendered via `details["inner_message"]` in the error envelope). **GATING:** same as above.
   - `test_no_recovery_source_e2e(tmp_path)`: bootstrap; delete BOTH state.json and journal.log; run `sdlc rebuild-state`; assert exit 2; stderr contains `"no journal at"` AND backup-dir hint.
8. **Coverage gate.** New modules `state/rebuild.py`, `cli/rebuild_state.py`, plus the `read_state_or_recover` addition in `state/reader.py`, MUST reach ≥ 90% line coverage. The existing global `--cov-fail-under=90` enforces this.

**And** all new test files include `from __future__ import annotations` as the first non-comment line + the module-level `pytestmark` declaration. Test classes are NOT used (project convention; bare functions only).

**And** the existing `tests/unit/state/test_state_projection.py`, `tests/unit/state/test_state_atomic_protocol.py`, `tests/unit/state/test_state_read.py`, `tests/property/test_replay_invariant.py`, `tests/chaos/test_atomic_write_kill_points.py` are ALL re-run unchanged. Story 1.20's additions are additive — no existing test should break.

**AC8 — ADR-023 records rebuild-state design + refuse-to-start gate**

**Given** NFR-MAINT-5 ("every load-bearing decision recorded as an ADR") AND existing ADRs 001-022 (latest at story-implement time may be 016-022 depending on which Stories 1.13-1.19 have landed),

**When** Story 1.20 lands,

**Then** `docs/decisions/ADR-023-rebuild-state-and-recovery-prompt.md` is authored using `docs/decisions/adr-template.md` covering:

1. **Status:** Accepted, dated to story-implement day.
2. **Context:** FR5, FR35, NFR-DR-1 mapping. Decision B4 (full replay from journal[0]) and B5 (state as projection of journal) from Architecture §348-§349. Stories 1.10 + 1.11 + 1.12 substrate (atomic write, append-only journal, projection). Story 1.19's schema gate (`read_state_or_refuse`) — Story 1.20 ADDS the recovery-prompt wrapper layer on top.
3. **Decision:**
   - `state/rebuild.py:rebuild_state_from_journal(journal_path, state_path) -> int` is the public recovery primitive. It composes `project_from_journal` (read) + `write_state_atomic_sync` (write); returns the count of replayed entries.
   - The function refuses with `StateError(reason="missing_journal")` when journal is absent — recovery from no source is impossible.
   - The function does NOT mutate the journal; it does NOT take a `--from-snapshot` parameter (full replay only in v1).
   - `cli/rebuild_state.py:run_rebuild_state(ctx)` is the user-facing Typer command. It pre-empts the missing-journal case with a backup-directory hint pointing to `.claude/state/backups/`.
   - `state/reader.py:read_state_or_recover(state_path, journal_path) -> State | None` is the canonical CLI-side state reader. It wraps Story 1.19's `read_state_or_refuse` and converts errors into a unified recovery prompt: `"state.json is malformed at <path>. To recover: run \`sdlc rebuild-state\` (rebuilds from journal) or \`sdlc migrate-vN\` (if version mismatch). The journal at <path> is untouched."`
   - All existing CLI subcommands that read state.json (`scan`, `status`, `trace`, `replay`, `logs`, `migrate-v\*`) are MIGRATED to call `read_state_or_recover` (NOT `read_state_or_refuse`).
   - The recovery prompt is unified across schema-mismatch and other malformations; the inner Story 1.19 message is preserved in `details["inner_message"]` for forensic / programmatic consumers.
   - The journal is NEVER touched on the malformed-state read path — `read_state_or_recover` does NOT call `iter_entries`. The `journal_path` parameter is purely for message formatting, reassuring the user that recovery is safe.
   - `MODULE_DEPS` is UNCHANGED — `state` already depends on `journal`; `cli` already depends on `state`.
   - Re-export `rebuild_state_from_journal` and `read_state_or_recover` from `sdlc.state` (with Windows shims).
4. **Alternatives considered:**
   - **Auto-rebuild on framework startup if state.json is missing / corrupt.** Rejected — silent recovery is a class of disaster (irreversible writes without user consent). Story 1.20 contract: refuse-with-clear-error + explicit user-invoked `sdlc rebuild-state`. Same rationale as Story 1.19's "never auto-migrate" policy.
   - **Single unified `sdlc recover` command that auto-detects rebuild vs migrate.** Rejected for v1 — the user's intent is meaningful (rebuild = "use the journal as source of truth"; migrate = "the journal is fine but the state schema bumped"). Conflating them risks data loss. PRD §511 commits to the surface `sdlc rebuild-state` and `sdlc migrate-vN` separately.
   - **Make `rebuild_state_from_journal` idempotent via a hash check (skip the atomic write if state.json already matches the projection bytes).** Rejected — the atomic write protocol is cheap and rebuild is not a hot loop. The optimisation adds complexity (hash equality check, race window between read and write) without real benefit.
   - **Add a `--snapshot <seq>` parameter for partial replay.** Deferred — Decision B4 explicitly defers snapshot caching. Performance signal would justify v1.x extension, not premature optimisation in v1.
   - **Add a `--from-backup <path>` parameter to restore from `.claude/state/backups/state.json.pre-migrate-vN.json`.** Deferred — Architecture §453's backup directory is migration-specific; arbitrary backup restore is a future story (Concern #13: backup retention). v1.20 is journal-only.
   - **Make the recovery prompt configurable (custom message via project.yaml).** Rejected — the recovery prompt is the disaster-recovery user experience; allowing custom wording invites confusion across projects. The format is locked via `_RECOVERY_MSG_FORMAT` constant.
   - **Use a SchemaError subclass (`MalformedStateError`) for the wrapped error instead of generic StateError.** Rejected — the generic StateError + `details["reason"]` discriminator is the established pattern (Story 1.10's `read_state` uses it; Story 1.19's `read_state_or_refuse` uses it). Adding a new subclass for one wrap site is premature ontology.
   - **Have `read_state_or_recover` ALSO read the journal and assert it parses cleanly before formatting the recovery prompt.** Rejected — that conflates the gate (which is about state.json) with journal validation (which is `cli/rebuild_state.py`'s job). Keeping the gate purely state.json-focused makes failures clearer (a malformed journal doesn't break the gate; the user runs `rebuild-state` and discovers the journal corruption then).
   - **Fall back to backups automatically when journal is missing.** Rejected — same auto-recovery anti-pattern as the auto-rebuild-on-startup case. v1.20 surfaces the backup-directory hint and lets the user decide.
5. **Consequences:**
   - All FR5 / FR35 / NFR-DR-1 requirements have user-facing surfaces. The framework refusal-on-malformed-state IS FR5; the rebuild command IS FR35.
   - Future stories (1.21 wire-format-lock, 2A.x onward) inherit the recovery posture: any new wire-format contract that gets persisted to disk MUST follow the same gate-with-recovery-prompt pattern.
   - Story 1.21 (Wire-Format v1.0 Lock) is INDEPENDENT — it locks the 5 wire-format contracts; this story locks the rebuild-state surface for state.json. The next-revisit-by date for ADR-023 is the first time a future story wants to add `sdlc rebuild-journal` (when journal corruption recovery becomes a user-facing command).
   - The "journal is untouched" reassurance in the recovery prompt becomes a load-bearing user-trust contract. Any future change that mutates the journal during a state-malformed-read path violates this contract — flagged in ADR-023.
   - `cli/main.py`'s registration grows by one static command (`rebuild-state`). The cold-start budget impact is negligible (deferred-import pattern; no work at module import).
   - The double-iteration over the journal in `rebuild_state_from_journal` (once for projection, once for count) is a deliberate trade-off documented inline. If recovery latency on a 100k-entry journal becomes a real problem, Story 1.x can refactor `project_from_journal` to return `(State, int)`.
6. **Revisit-by:** First time journal corruption becomes a user-facing recovery scenario (triggers `sdlc rebuild-journal` design). First time backup-restore is added as a CLI surface. First time the recovery prompt format is changed (e.g., to add a third recovery option).
7. **References:** PRD §377 (recovery from corruption), §511 (CLI surface includes `sdlc rebuild-state`), §660 (fallback if init fails), §727 (FR5 verbatim), §769 (FR35 verbatim), §899 (NFR-DR-1 verbatim). Architecture §139 (DR mapping), §348 (Decision B4 — full replay), §349 (Decision B5 — state as projection), §453 (backup directory layout), §589 (kill-between-7-and-8 recovery scenario), §805 (`cli/rebuild_state.py`), §841-§846 (`state/` layout), §1059 (state surface includes `rebuild_state`), §1135 (FR5 → `state/reader.py`), §1161 (FR35 → `cli/rebuild_state.py + state/rebuild.py`), §1278 (disaster-recovery surface). ADR-013 (atomic write — Story 1.10), ADR-014 (append-only journal — Story 1.11), ADR-015 (state projection — Story 1.12), ADR-022 (migration framework + schema gate — Story 1.19, if shipped at story-implement time).

**And** `docs/decisions/index.md` gains the row `| [023](ADR-023-rebuild-state-and-recovery-prompt.md) | sdlc rebuild-state + unified recovery prompt | 1.20 | Accepted |` after the most recent ADR row. If 016-022 haven't all shipped at story-implement time, take the next free number after the latest ADR on disk.

## Tasks / Subtasks

- [ ] **Task 1: Pre-flight verification of dependencies, environment, and prior-story state (AC: all)**
  - [ ] Verify Story 1.10 deliverables on disk: `src/sdlc/state/atomic.py` exports `write_state_atomic_sync`. Smoke: `uv run python -c "from sdlc.state import write_state_atomic_sync; print('ok')"`. Sprint-status `1-10: done`.
  - [ ] Verify Story 1.11 deliverables on disk: `src/sdlc/journal/writer.py` exports `append_sync`; `src/sdlc/journal/reader.py` exports `iter_entries`. Smoke: `uv run python -c "from sdlc.journal import append_sync, iter_entries; print('ok')"`. Sprint-status `1-11: done`.
  - [ ] Verify Story 1.12 deliverables on disk: `src/sdlc/state/projection.py` exports `project_from_journal`. Smoke: `uv run python -c "from sdlc.state import project_from_journal; print('ok')"`. Sprint-status `1-12: done`.
  - [ ] Verify Story 1.16 deliverables on disk (or in-flight): `src/sdlc/cli/main.py` (with `app` Typer instance + global `--no-color` / `--json` callback), `src/sdlc/cli/output.py` (with `emit_error`, `emit_json`, `make_console`, `is_no_color_active`, `echo`). **GATING:** if 1.16 is NOT `done` (sprint-status `1-16: ready-for-dev` per snapshot 2026-05-09), HALT and surface as a blocking dependency. Story 1.20 fundamentally extends 1.16's CLI scaffolding — without it, `app.command(name="rebuild-state")` has no `app` to register against.
  - [ ] Verify Story 1.17 deliverables on disk (or in-flight): `cli/output.py` extended with `_ERR_CODE_TO_EXIT_CODE` table including `ERR_NOT_INITIALIZED`, `ERR_INFRASTRUCTURE`. **GATING (soft):** Story 1.20 adds new error codes (`ERR_NO_RECOVERY_SOURCE`, `ERR_JOURNAL_CORRUPT`, `ERR_JOURNAL_SCHEMA_DRIFT`) to the same table. If 1.17 has not landed, add the entries to whichever revision of `cli/output.py` IS on disk.
  - [ ] Verify Story 1.19 deliverables on disk (or in-flight): `src/sdlc/state/reader.py` exports `read_state_or_refuse`, `read_state_raw`, `CURRENT_SCHEMA_VERSION`; `_REFUSAL_MSG_FORMAT` constant. **GATING (HARD):** Story 1.20's AC5 (`read_state_or_recover`) wraps Story 1.19's `read_state_or_refuse`. If 1.19 has NOT landed, Story 1.20 MUST either (a) wait for 1.19 OR (b) implement BOTH `read_state_or_refuse` AND `read_state_or_recover` in the same patch. Document the chosen path in dev notes; coordinate with the planner.
  - [ ] Verify ADR numbering: existing ADRs are 001-016 per `ls docs/decisions/ADR-*.md` (snapshot 2026-05-09). ADRs 017-022 are in flight per Stories 1.13-1.19; Story 1.20 (this story) authors **ADR-023**. Take next free number after the most recent ADR on disk at story-implement time.
  - [ ] Verify `pyproject.toml [project] dependencies` includes `pydantic>=2,<3` (Story 1.7), `typer>=0.12,<1` (Story 1.16), `hypothesis>=6.100` (Story 1.7 dev-dep). Story 1.20 ADDS NO new third-party dependencies — `pathlib`, `sys`, `logging` are stdlib.
  - [ ] Verify `src/sdlc/state/rebuild.py` does NOT exist on disk. If exists (half-merged earlier story or stale scaffold), HALT and reconcile manually.
  - [ ] Verify `src/sdlc/cli/rebuild_state.py` does NOT exist on disk.
  - [ ] Verify `tests/unit/state/test_rebuild.py`, `tests/property/test_rebuild_invariant.py`, `tests/unit/cli/test_rebuild_state.py`, `tests/integration/test_rebuild_state_e2e.py` do NOT exist.
  - [ ] Verify `docs/decisions/ADR-023-rebuild-state-and-recovery-prompt.md` does NOT exist.
  - [ ] Verify the existing pre-commit hooks pass on `main`: `uv run pre-commit run --all-files`. Establish a green baseline before mutating.
  - [ ] Verify the existing test suite passes: `uv run pytest -q`. All green.

- [ ] **Task 2: Bootstrap `src/sdlc/state/rebuild.py` (AC: #1)**
  - [ ] Create `src/sdlc/state/rebuild.py` with the module docstring from AC1.1.
  - [ ] First non-comment line: `from __future__ import annotations`.
  - [ ] Add the POSIX-only platform guard (AC1.6) BEFORE other imports:
    ```python
    import sys
    if sys.platform == "win32":
        raise ImportError(
            "sdlc.state.rebuild is POSIX-only — depends on state.atomic"
            " (Architecture §573)"
        )
    ```
  - [ ] Stdlib imports: `from pathlib import Path`, `from typing import Final`.
  - [ ] Project imports per AC1.2: `from sdlc.errors import StateError`, `from sdlc.journal import iter_entries`, `from sdlc.state.atomic import write_state_atomic_sync`, `from sdlc.state.projection import project_from_journal`. Note: `JournalError` is NOT caught here (propagates per AC1.3).
  - [ ] Implement `rebuild_state_from_journal(journal_path: Path, state_path: Path) -> int` per AC1.3:
    1. Validate journal_path is absolute → `StateError(step="validate_journal_path")` if not.
    2. Validate state_path is absolute → `StateError(step="validate_state_path")` if not.
    3. Refuse on missing journal → `StateError(reason="missing_journal")`.
    4. `state = project_from_journal(journal_path)` (may raise `JournalError`; propagate).
    5. `entries_replayed = sum(1 for _ in iter_entries(journal_path))`.
    6. `write_state_atomic_sync(state, state_path)` (may raise `StateError`; propagate).
    7. Return `entries_replayed`.
  - [ ] Define `__all__ = ("rebuild_state_from_journal",)  # noqa: RUF022`.
  - [ ] Run `uv run mypy --strict src/sdlc/state/rebuild.py` → must pass.
  - [ ] Run `uv run ruff check src/sdlc/state/rebuild.py` and `uv run ruff format --check src/sdlc/state/rebuild.py` → both pass.
  - [ ] LOC ≤ 80. Confirm via `wc -l`.

- [ ] **Task 3: Update `src/sdlc/state/__init__.py` re-export (AC: #4)**
  - [ ] Open `src/sdlc/state/__init__.py`. Locate the `if sys.platform != "win32":` block (currently lines 9-10).
  - [ ] Append `from sdlc.state.rebuild import rebuild_state_from_journal` to the POSIX branch.
  - [ ] In the `else:` branch, append the Windows shim (AC4.2) — return type `int` to match production signature for mypy.
  - [ ] Update `__all__` per AC4.3 — append `"rebuild_state_from_journal"` at the end. **CRITICAL:** if Story 1.19's additions (`read_state_or_refuse`, `read_state_raw`, `write_state_raw_atomic_sync`, `CURRENT_SCHEMA_VERSION`) are NOT yet in `__all__` (because 1.19 hasn't landed), ADD ONLY `"rebuild_state_from_journal"` — do NOT speculatively add 1.19's symbols. The eventual merge produces the union.
  - [ ] Smoke: `uv run python -c "from sdlc.state import rebuild_state_from_journal; print('ok')"` → prints `ok`.
  - [ ] Run `uv run mypy --strict src/sdlc/state/` → must pass.
  - [ ] Run `uv run ruff check src/sdlc/state/` → must pass.

- [ ] **Task 4: Add `read_state_or_recover` to `src/sdlc/state/reader.py` (AC: #5)**
  - [ ] **GATING:** confirm Story 1.19's `state/reader.py` exists. If not, this task implements BOTH the Story 1.19 symbols AND Story 1.20's wrapper in one patch (coordinate with whoever owns 1.19).
  - [ ] Open `src/sdlc/state/reader.py`. Add the `_RECOVERY_MSG_FORMAT` constant per AC5.2 alongside Story 1.19's `_REFUSAL_MSG_FORMAT`.
  - [ ] Implement `read_state_or_recover(state_path: Path, journal_path: Path) -> State | None` per AC5.3. The function MUST:
    - Call `read_state_or_refuse(state_path)` first.
    - On `SchemaError` (Story 1.19 schema_version mismatch): wrap into a NEW `StateError` with the `_RECOVERY_MSG_FORMAT` message + merged details + `__cause__` chain.
    - On `StateError` (Story 1.19 other malformations): wrap into a NEW `StateError` with the `_RECOVERY_MSG_FORMAT` message + merged details + `__cause__` chain.
    - Note: Story 1.19's `SchemaError` becomes `StateError` here — the gate UNIFIES the user-facing class.
  - [ ] Update `state/reader.py:__all__` to append `"read_state_or_recover"` (AC5.4).
  - [ ] Update `state/__init__.py` (extend Task 3): add `read_state_or_recover` to the POSIX import + Windows shim (return type `None`); add to `__all__`.
  - [ ] Run `uv run mypy --strict src/sdlc/state/reader.py` → must pass.
  - [ ] Run `uv run ruff check src/sdlc/state/reader.py` → must pass.
  - [ ] LOC of `state/reader.py` stays under Story 1.19's cap (≤ 200 with the 1.20 addition).

- [ ] **Task 5: Bootstrap `src/sdlc/cli/rebuild_state.py` (AC: #2)**
  - [ ] Create `src/sdlc/cli/rebuild_state.py` with the module docstring from AC2.1.
  - [ ] First non-comment line: `from __future__ import annotations`.
  - [ ] Top-level imports + module-level constants per AC2.2 (deferred imports stay inside function bodies).
  - [ ] Implement `_get_repo_root_or_cwd()` (or import from `cli/_paths.py` if it exists from Stories 1.16-1.18).
  - [ ] Implement `_resolve_paths(repo_root: Path) -> tuple[Path, Path, Path]` returning `(state_path, journal_path, backup_dir)`.
  - [ ] Implement `_check_initialized_or_refuse(ctx: typer.Context, state_dir: Path) -> None` per AC2.3 Step 2.
  - [ ] Implement `_check_recovery_source_or_refuse(ctx: typer.Context, state_path: Path, journal_path: Path, backup_dir: Path) -> None` per AC2.3 Steps 3-4.
  - [ ] Implement `_dispatch_rebuild_error(ctx: typer.Context, err: Exception, state_path: Path, journal_path: Path, backup_dir: Path) -> None` per AC2.3 Step 5 — the error-mapping table (or if-tree).
  - [ ] Implement `_emit_success(ctx: typer.Context, entries_replayed: int, state_path: Path, journal_path: Path) -> None` — handles human + JSON modes per AC2.3 Step 6.
  - [ ] Implement `run_rebuild_state(ctx: typer.Context) -> None` — orchestrator following the 6-step flow in AC2.3.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/rebuild_state.py` → must pass.
  - [ ] Run `uv run ruff check src/sdlc/cli/rebuild_state.py` → must pass.
  - [ ] LOC ≤ 200. Confirm.

- [ ] **Task 6: Add error codes to `cli/output.py` envelope mapping (AC: #2)**
  - [ ] Locate `cli/output.py`'s `_ERR_CODE_TO_EXIT_CODE` table (extended by Stories 1.16-1.18-1.19). Append the new entries IN ORDER (preserve prior story order; do NOT alphabetize):
    ```python
    # Added in Story 1.20 — see ADR-023.
    "ERR_NO_RECOVERY_SOURCE": 2,
    "ERR_JOURNAL_CORRUPT": 2,
    "ERR_JOURNAL_SCHEMA_DRIFT": 2,
    ```
  - [ ] Update the module docstring to reference Story 1.20's added codes (one-line addition).
  - [ ] Verify LOC of `cli/output.py` stays within Story 1.18's cap.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/output.py` → must pass.

- [ ] **Task 7: Extend `cli/main.py` with `rebuild-state` command (AC: #3)**
  - [ ] Open `src/sdlc/cli/main.py`. After the existing subcommand registrations (init/scan/status/trace/replay/logs/migrate-vN), add the `@app.command(name="rebuild-state")` registration per AC3.2.
  - [ ] The command body uses the deferred-import pattern: `from sdlc.cli.rebuild_state import run_rebuild_state` inside the function body.
  - [ ] Verify cold-start budget. Run `uv run python -c "import time; t=time.perf_counter(); import sdlc.cli.main; print(round((time.perf_counter()-t)*1000, 2), 'ms')"` — MUST stay < 200 ms. Run 5 iterations; report median.
  - [ ] Run `uv run sdlc --help` — assert `rebuild-state` appears in the subcommand list.
  - [ ] Run `uv run mypy --strict src/sdlc/cli/main.py` → must pass.

- [ ] **Task 8: Migrate existing CLI subcommands to use `read_state_or_recover` (AC: #6)**
  - [ ] Run `grep -rln "read_state_or_refuse\|read_state(" src/sdlc/cli/` to enumerate touched files.
  - [ ] For each file in the enumeration (EXCEPT `init.py` and `rebuild_state.py`):
    - [ ] Replace `from sdlc.state import read_state_or_refuse` with `from sdlc.state import read_state_or_recover`.
    - [ ] Replace `read_state_or_refuse(state_path)` calls with `read_state_or_recover(state_path, journal_path)`. Construct `journal_path` from `<repo_root> / .claude/state/journal.log` near the existing state_path computation.
    - [ ] Update `try/except StateError` blocks to handle the new `details["state_path"]` / `details["journal_path"]` keys when emitting via `emit_error`.
    - [ ] Remove any `except SchemaError` blocks for the v1.19 schema-mismatch case — `read_state_or_recover` re-raises as `StateError` (the Story 1.19 SchemaError is preserved in `__cause__` for forensic logging).
  - [ ] Run `uv run mypy --strict src/sdlc/cli/` → must pass.
  - [ ] Run `uv run pytest tests/unit/cli/ -m unit` → all existing tests still pass (the gate change is behaviorally invisible for the success path; failure messages now include the recovery prompt).

- [ ] **Task 9: Author all unit tests (AC: #7.1, #7.3, #7.4, #7.6)**
  - [ ] Create `tests/unit/state/test_rebuild.py` per AC7.1.
  - [ ] Extend `tests/unit/state/test_reader.py` (Story 1.19's file) with the 8 tests from AC7.3. If Story 1.19 hasn't shipped, CREATE `test_reader.py` with both 1.19's and 1.20's tests.
  - [ ] Create `tests/unit/cli/test_rebuild_state.py` per AC7.4.
  - [ ] Extend `tests/unit/cli/test_main.py` with the 2 tests from AC7.6.
  - [ ] Each test file: `from __future__ import annotations` + module-level `pytestmark` declaration with POSIX-skipif where appropriate.
  - [ ] Smoke: `uv run pytest tests/unit/state/test_rebuild.py tests/unit/state/test_reader.py tests/unit/cli/test_rebuild_state.py -v` — every test passes.
  - [ ] Run full unit suite: `uv run pytest tests/unit/ -m unit` — every test passes; coverage ≥ 90% on the new modules.

- [ ] **Task 10: Author property tests (AC: #7.2)**
  - [ ] Create `tests/property/test_rebuild_invariant.py` per AC7.2.
  - [ ] Import the `monotonic_sequence_strategy` from `tests/property/test_replay_invariant.py` (Story 1.12) — do NOT duplicate the strategy.
  - [ ] Implement the 3 property tests from AC7.2.
  - [ ] Smoke: `uv run pytest tests/property/test_rebuild_invariant.py -v` — every test passes; hypothesis runs to default budget.

- [ ] **Task 11: Author chaos test extension (AC: #7.5, OPTIONAL)**
  - [ ] If chaos coverage of rebuild is in scope: extend `tests/chaos/test_atomic_write_kill_points.py` per AC7.5.
  - [ ] If deferred: add a deferred-work entry citing Story 1.20 review.

- [ ] **Task 12: Author integration tests (AC: #7.7)**
  - [ ] Create `tests/integration/test_rebuild_state_e2e.py` with `pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")]`.
  - [ ] Implement the 4 tests from AC7.7. **GATING:** if Story 1.17's `sdlc status` hasn't shipped, swap with whichever subcommand HAS shipped. Document the swap in test docstrings.
  - [ ] Smoke: `uv run pytest tests/integration/test_rebuild_state_e2e.py -v` — every test passes.

- [ ] **Task 13: Author ADR-023 (AC: #8)**
  - [ ] Create `docs/decisions/ADR-023-rebuild-state-and-recovery-prompt.md` using the template at `docs/decisions/adr-template.md`.
  - [ ] Fill in Status, Context, Decision, Alternatives, Consequences, Revisit-by, References per AC8.
  - [ ] Update `docs/decisions/index.md` with the new row per AC8 closing.
  - [ ] If ADR-017 through ADR-022 are missing on disk (because Stories 1.13-1.19 haven't all landed), use the next-free number AFTER the latest ADR on disk. Re-number the index row accordingly.

- [ ] **Task 14: Smoke + integration sanity (AC: all)**
  - [ ] In a tmp dir: `git init && uv run sdlc init`. Verify `.claude/state/state.json` and (eventually) `.claude/state/journal.log` exist.
  - [ ] Manually inject 3 journal entries via in-process Python (`uv run python -c "from sdlc.journal import append_sync; ..."`).
  - [ ] Delete `.claude/state/state.json`. Run `uv run sdlc rebuild-state`. Verify exit 0; stdout contains `"state rebuilt from 3 journal entries"`. Verify state.json now exists with the projected content.
  - [ ] Run `uv run sdlc rebuild-state` AGAIN (idempotency). Verify exit 0; verify state.json bytes UNCHANGED.
  - [ ] Delete BOTH state.json and journal.log. Run `uv run sdlc rebuild-state`. Verify exit 2; stderr contains `"no journal at"` AND backup-directory hint.
  - [ ] Restore both files. Manually overwrite state.json with `not-json`. Run `uv run sdlc status` (or whichever subcommand reads state.json). Verify exit 2; stderr contains `"state.json is malformed at"` AND `"sdlc rebuild-state"` AND `"sdlc migrate-vN"` AND `"is untouched"`.
  - [ ] Run `uv run sdlc rebuild-state` (recovery from the malformed state). Verify exit 0; stdout contains the success message; verify state.json is now valid.
  - [ ] Manually overwrite state.json with `{"schema_version":2, "next_monotonic_seq":0, "epics":{}}`. Run `uv run sdlc status`. Verify exit 2; stderr contains the recovery prompt AND the inner Story 1.19 message `"schema_version mismatch: state is v2, framework expects v1"`.
  - [ ] Run all pre-commit hooks: `uv run pre-commit run --all-files`. All green.
  - [ ] Run full test suite: `uv run pytest -v --cov=src --cov-fail-under=90`. All green; coverage ≥ 90%.
  - [ ] Address deferred-work items now in scope:
    - [ ] `tests/property/test_replay_invariant.py` Windows CI blind spot — replace `append_sync` calls with direct `_canonicalize_entry` + `Path.write_bytes` so the read-path tests run on Windows. Document the rewrite in dev notes.
    - [ ] `journal/reader.py` partial-consumption recovery contract — document in `state/rebuild.py` docstring that on `JournalError("reader_invariant")`, the caller MUST treat the rebuild as failed; partial consumption is NOT a recovery state. ADR-023 records the contract.

## Dev Notes

### Architecture and Pattern References

- **Decision B4 (full replay from journal[0])** — Architecture §348. Story 1.20's `rebuild_state_from_journal` is the materialisation: it composes `project_from_journal` + `write_state_atomic_sync`. Snapshot caching is deferred to v1.x; the function does NOT take a `--from-snapshot` parameter.
- **Decision B5 (state as projection of journal)** — Architecture §349. Story 1.20 makes the projection user-recoverable: when state.json is lost or corrupted, the user can rebuild via `sdlc rebuild-state` because the journal is the source of truth.
- **Story 1.10 atomic write protocol** — `state/atomic.py:write_state_atomic_sync`. Story 1.20 invokes this for the rebuild's final write step. The 7-step POSIX protocol guarantees: a kill mid-rebuild leaves either (a) the prior state.json (if any) intact OR (b) the new rebuilt state.json. Never partial.
- **Story 1.11 journal append-only protocol** — `journal/writer.py`. Story 1.20 NEVER touches the journal — read-only access via `iter_entries`. The "journal is untouched" reassurance in the recovery prompt is a load-bearing user-trust contract.
- **Story 1.12 state projection** — `state/projection.py:project_from_journal`. Story 1.20 invokes this for the rebuild's read step. The replay invariant `project_from_journal(journal[0:k]) == state_at_step_k` for every k (Story 1.12 property test) GUARANTEES Story 1.20's byte-equivalence claim (AC1 + AC7.2).
- **Story 1.19 schema gate** — `state/reader.py:read_state_or_refuse`. Story 1.20 wraps this with `read_state_or_recover` to add the unified recovery prompt. The wrapping is idempotent: a `read_state_or_refuse(target)` call followed by `read_state_or_recover(target, journal_path)` produces the same StateError for malformations (just with extra `details` keys and a wrapper message).
- **Recovery convention** — Architecture §453. The backup directory `.claude/state/backups/` is migration-specific (per Story 1.19), but Story 1.20's CLI hint points users there for forensic inspection when journal recovery is impossible.
- **CLI cold-start discipline** — Architecture §488. `cli/rebuild_state.py` and `cli/main.py`'s `rebuild-state` registration use deferred imports for `sdlc.state.rebuild_state_from_journal` and `sdlc.errors`. The cold-start budget is unchanged.
- **CLI exit-code discipline** — Architecture §540-§548. Recovery errors are exit 2 (framework / schema violation); not-initialized is exit 1 (user error); infrastructure errors (I/O failure during atomic write) are exit 3.
- **POSIX-only stance** — Architecture §573. Both `state/rebuild.py` and `cli/rebuild_state.py` are POSIX-only via the transitive dependency on `state/atomic.py` (which requires `fcntl` + `O_APPEND`). Windows shims raise `NotImplementedError`.

### Forward-Compat Seams (intentional, documented)

1. **No `--from-snapshot` flag in v1.20.** Decision B4 defers snapshot caching. When v1.x adds snapshots, `rebuild_state_from_journal` will gain an optional `from_snapshot: ResumeToken | None = None` parameter. The current single-arg signature is forward-compatible (Python's keyword-default pattern).
2. **No `--from-backup <path>` flag in v1.20.** Future story will add backup-restore as a CLI surface (Concern #13 — backup retention). v1.20's CLI hint to `.claude/state/backups/` is the bridge.
3. **No `sdlc rebuild-journal` command in v1.20.** Journal corruption recovery is a future story. When it lands, the recovery prompt may be augmented with "or `sdlc rebuild-journal` (if journal is corrupt)".
4. **No `--dry-run` flag.** Forensics use case is real but deferred. Users can `cp state.json state.json.bak` before running.
5. **Recovery prompt format is locked.** `_RECOVERY_MSG_FORMAT` is a module-level constant. Changing the format is a breaking change — callers / tests that substring-match on `"sdlc rebuild-state"` or `"is untouched"` would break. Document in ADR-023 that the format is part of the public CLI contract.
6. **`read_state_or_recover` is the canonical reader.** All future CLI subcommands that read state.json MUST use it. The discipline is documented in `state/reader.py` docstring + ADR-023.
7. **The "journal is untouched" reassurance is load-bearing.** Any future change that mutates the journal during a state-malformed-read path (or during a rebuild operation) violates the user-trust contract. Flagged in ADR-023's Consequences.
8. **Double-iteration over journal is a deliberate trade-off.** `rebuild_state_from_journal` reads the journal twice (once in `project_from_journal`, once for entry count). Acceptable: recovery is not a hot loop. Refactor to `(State, int)` tuple is a v1.x optimisation when latency signal justifies it.
9. **`SchemaError → StateError` unification.** Story 1.20's `read_state_or_recover` re-raises Story 1.19's `SchemaError` as `StateError`. Callers that catch `SdlcError` (parent class) are unaffected. Callers that specifically catch `SchemaError` MUST switch to `StateError` OR to `SdlcError`. Document in ADR-023's Consequences.

### Critical Disaster-Prevention Reminders

- **Never auto-rebuild on framework startup.** A silent rebuild is a class of disaster (the user's state.json corruption may be a SYMPTOM of a worse bug; auto-rebuilding masks it). Story 1.20's contract: refuse-with-clear-error-message + explicit user-invoked `sdlc rebuild-state`. Same rationale as Story 1.19's "never auto-migrate" policy.
- **Never mutate the journal during rebuild.** The journal is the source of truth (Decision B5). Mutating it during rebuild creates a chicken-and-egg recovery loop. The `read_state_or_recover` function does NOT call `iter_entries`; the `rebuild_state_from_journal` function calls `iter_entries` only for read.
- **Never write state.json without going through `write_state_atomic_sync`.** The 7-step protocol is the only way to guarantee kill-safety. Direct `Path.write_text` calls would leave a partial file on power-loss. The `check_no_direct_state_writes.py` linter (Story 1.10) enforces this.
- **Never delete the journal as part of recovery.** Even if `sdlc rebuild-state` fails (e.g., journal is corrupt), the journal is the user's only recoverable artifact. The recovery prompt explicitly says "is untouched" — keep that promise.
- **Never confuse "state.json missing" with "state.json malformed".** Missing → `read_state_or_refuse` returns `None` → caller surfaces `ERR_NOT_INITIALIZED` (exit 1) → user runs `sdlc init`. Malformed → `read_state_or_recover` raises `StateError` with recovery prompt → user runs `sdlc rebuild-state`. Story 1.20's gate distinguishes the two.
- **Never strip the `__cause__` chain.** `read_state_or_recover` MUST use `raise ... from err` to preserve the original Story 1.19 error. Forensic logging downstream depends on the chain.
- **Never use `read_state_or_recover` from the rebuild command itself.** `cli/rebuild_state.py` reads the journal, not state.json — the gate would be misapplied. The exception list in `state/reader.py` docstring (init, rebuild-state) is enforced by code review.

### Project Structure Notes

- **New files:** `src/sdlc/state/rebuild.py`, `src/sdlc/cli/rebuild_state.py`, `tests/unit/state/test_rebuild.py`, `tests/property/test_rebuild_invariant.py`, `tests/unit/cli/test_rebuild_state.py`, `tests/integration/test_rebuild_state_e2e.py`, `docs/decisions/ADR-023-rebuild-state-and-recovery-prompt.md`.
- **Modified files:** `src/sdlc/state/__init__.py` (export `rebuild_state_from_journal` + `read_state_or_recover` + Windows shims), `src/sdlc/state/reader.py` (add `_RECOVERY_MSG_FORMAT` + `read_state_or_recover` + extend `__all__`), `src/sdlc/cli/main.py` (add `rebuild-state` registration), `src/sdlc/cli/output.py` (add 3 new error codes), `src/sdlc/cli/{scan,status,trace,replay,logs,migrate}.py` (migrate from `read_state_or_refuse` to `read_state_or_recover` per AC6), `tests/unit/cli/test_main.py` (extend), `tests/unit/state/test_reader.py` (extend Story 1.19's file with the 8 tests from AC7.3), `docs/decisions/index.md` (ADR row).
- **Detected variances:** None — the architecture's `state/rebuild.py` (§846) and `cli/rebuild_state.py` (§805) layout is honored exactly. The only minor adjustment: `state/rebuild.py` is POSIX-only (architecture doesn't explicitly state this, but the transitive dep on `state/atomic.py` makes it inevitable).
- **No new third-party dependencies.** Story 1.20 uses stdlib (`pathlib`, `sys`, `logging`) + existing `pydantic`, `typer` from prior stories.
- **MODULE_DEPS unchanged.** `state` already depends on `journal` (per Story 1.12). `cli` already depends on `state` (per Story 1.16). No `scripts/check_module_boundaries.py` edits required.

### Test Coverage Analysis

- **Unit:** `state/rebuild.py` covered by `tests/unit/state/test_rebuild.py` (12 tests); `state/reader.py:read_state_or_recover` covered by `tests/unit/state/test_reader.py` extension (8 tests); `cli/rebuild_state.py` covered by `tests/unit/cli/test_rebuild_state.py` (12 tests). Total new unit test count: ~32.
- **Property:** Byte-equivalence + idempotency + entry-count over hypothesis-generated journals (3 tests in `tests/property/test_rebuild_invariant.py`).
- **Chaos:** OPTIONAL — extends Story 1.10's kill-point matrix with the rebuild path (10 KillPoints × parametrize). Defer if scope is tight; document.
- **Integration:** End-to-end via subprocess `uv run sdlc` (4 tests in `tests/integration/test_rebuild_state_e2e.py`).
- **Coverage gate:** ≥ 90% on new modules; existing global threshold enforces.

### References

- [Source: docs/decisions/ADR-013-atomic-state-write-protocol.md] — atomic write protocol (Story 1.10) — the protocol body that `rebuild_state_from_journal` invokes via `write_state_atomic_sync`.
- [Source: docs/decisions/ADR-014-append-only-journal-protocol.md] — journal append-only invariant (Story 1.11) — informs why `rebuild_state_from_journal` reads but does NOT mutate the journal.
- [Source: docs/decisions/ADR-015-state-projection-from-journal.md] — state-as-projection (Story 1.12) — establishes the replay invariant Story 1.20's byte-equivalence claim depends on.
- [Source: src/sdlc/state/atomic.py:174-214] — `write_state_atomic` + `write_state_atomic_sync` — the production write API Story 1.20 composes.
- [Source: src/sdlc/state/atomic.py:217-245] — `read_state` — redirected by Story 1.19 to `read_state_or_refuse`; Story 1.20 wraps with `read_state_or_recover`.
- [Source: src/sdlc/state/projection.py:55-95] — `_project_entries` + `project_from_journal` — the read API Story 1.20 composes.
- [Source: src/sdlc/journal/reader.py:22-76] — `iter_entries` — read API for the entry-count step + the second-line-of-defence seq-regression check that propagates as `JournalError("reader_invariant")`.
- [Source: src/sdlc/journal/writer.py:163-200] — `_append_protocol_body` — informs why Story 1.20's rebuild does NOT touch the writer (read-only path).
- [Source: src/sdlc/state/model.py:10-22] — `State` pydantic model with `schema_version: int = 1` default and `extra="forbid"` — the projection target.
- [Source: src/sdlc/contracts/journal_entry.py:20-53] — `JournalEntry` with `schema_version: Literal[1] = 1` — the parse-time-rejection precedent for journal-side schema drift.
- [Source: src/sdlc/errors/base.py:6-71] — `SdlcError`, `StateError`, `SchemaError`, `JournalError`, `EXIT_CODE_MAP` — the error envelope this story extends.
- [Source: scripts/check_module_boundaries.py:50-59] — `MODULE_DEPS["state"]` (depends_on includes `journal` post-Story-1.12) — confirms no boundary changes needed.
- [Source: scripts/check_module_boundaries.py:134-137] — `MODULE_DEPS["cli"]` (depends_on includes `state`) — confirms no boundary changes needed.
- [Source: tests/property/test_replay_invariant.py] — Story 1.12's `monotonic_sequence_strategy` — imported (NOT duplicated) by Story 1.20's property tests.
- [Source: tests/chaos/kill_points.py] — Story 1.10's KillPoint enum (10 points) — extended by Story 1.20's optional chaos test.
- [Source: \_bmad-output/planning-artifacts/architecture.md#139] — DR mapping: "rebuild-state from journal".
- [Source: \_bmad-output/planning-artifacts/architecture.md#348-349] — Decision B4 (full replay from journal[0]) + Decision B5 (state as projection of journal) — load-bearing rationale.
- [Source: \_bmad-output/planning-artifacts/architecture.md#441-453] — backup file naming + `.claude/state/backups/` canonical layout — informs CLI hint.
- [Source: \_bmad-output/planning-artifacts/architecture.md#488] — CLI cold-start budget < 200 ms.
- [Source: \_bmad-output/planning-artifacts/architecture.md#501-508] — JSON canonicalization (NFC + sort_keys + separators).
- [Source: \_bmad-output/planning-artifacts/architecture.md#540-559] — error envelope + exit code mapping.
- [Source: \_bmad-output/planning-artifacts/architecture.md#569-589] — atomic write protocol (kill-between-7-and-8 recovery scenario at §589).
- [Source: \_bmad-output/planning-artifacts/architecture.md#727-745] — "atomic mutation" pattern that the rebuild's atomic write follows.
- [Source: \_bmad-output/planning-artifacts/architecture.md#791-810] — `cli/` module layout including `cli/rebuild_state.py` (§805).
- [Source: \_bmad-output/planning-artifacts/architecture.md#841-846] — `state/` module layout including `state/rebuild.py` (§846).
- [Source: \_bmad-output/planning-artifacts/architecture.md#1059] — `state` module surface includes `rebuild_state`.
- [Source: \_bmad-output/planning-artifacts/architecture.md#1135] — FR5 module mapping: `state/reader.py + cli/migrate.py`.
- [Source: \_bmad-output/planning-artifacts/architecture.md#1161] — FR35 module mapping: `cli/rebuild_state.py + state/rebuild.py`.
- [Source: \_bmad-output/planning-artifacts/architecture.md#1278] — disaster-recovery surface: `state/rebuild.py`.
- [Source: \_bmad-output/planning-artifacts/prd.md#377] — recovery from corruption (PRD-named user journey).
- [Source: \_bmad-output/planning-artifacts/prd.md#511] — CLI surface includes `sdlc rebuild-state`.
- [Source: \_bmad-output/planning-artifacts/prd.md#660] — fallback if init fails: `sdlc rebuild-state` ships in v1.
- [Source: \_bmad-output/planning-artifacts/prd.md#727] — FR5 verbatim: refusal on malformed state.
- [Source: \_bmad-output/planning-artifacts/prd.md#769] — FR35 verbatim: rebuild from journal.
- [Source: \_bmad-output/planning-artifacts/prd.md#899] — NFR-DR-1 verbatim: integration test asserts rebuild produces equivalent state.
- [Source: \_bmad-output/planning-artifacts/epics.md#906-930] — Story 1.20 epic AC verbatim.
- [Source: \_bmad-output/implementation-artifacts/deferred-work.md#"Reader yields half a stream"] — owned by Story 1.20 per the deferred-work registry.
- [Source: \_bmad-output/implementation-artifacts/deferred-work.md#"Windows CI blind spot"] — partially owned by Story 1.20 (cross-platform test rewrite).
- [Source: \_bmad-output/implementation-artifacts/1-19-migration-framework-major-version-refusal.md] — Story 1.19's `state/reader.py` + `read_state_or_refuse` + `_REFUSAL_MSG_FORMAT` — Story 1.20's wrapping target.

## Dev Agent Record

### Agent Model Used

(populated at implementation time)

### Debug Log References

### Completion Notes List

### File List

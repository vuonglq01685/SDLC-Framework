"""sdlc rebuild-state — disaster recovery from journal (FR35, NFR-DR-1, Architecture §805, §1161).

Reconstructs ``.claude/state/state.json`` from ``.claude/state/journal.log``
via ``sdlc.state.rebuild.rebuild_state_from_journal``. Refuses when the
journal is missing (no recovery source); points the user to backups
at ``.claude/state/backups/`` (Architecture §453). Idempotent:
re-running on a clean rebuild produces byte-identical state.json.

Does NOT touch the journal — read-only with respect to journal.log.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import typer

from sdlc.cli.output import echo, emit_error, emit_json

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_BACKUP_DIR_REL: Final[str] = ".claude/state/backups"


def _get_repo_root_or_cwd() -> Path:
    from sdlc.cli._paths import get_repo_root_or_cwd

    return get_repo_root_or_cwd()


def _resolve_paths(repo_root: Path) -> tuple[Path, Path, Path]:
    state_path = (repo_root / _STATE_PATH_REL).resolve()
    journal_path = (repo_root / _JOURNAL_PATH_REL).resolve()
    backup_dir = (repo_root / _BACKUP_DIR_REL).resolve()
    return state_path, journal_path, backup_dir


def _check_initialized_or_refuse(ctx: typer.Context, state_dir: Path, repo_root: Path) -> None:
    if not state_dir.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {repo_root}; run `sdlc init` first",
            ctx=ctx,
            details={"path": str(state_dir), "project_root": str(repo_root)},
        )


def _check_recovery_source_or_refuse(
    ctx: typer.Context,
    state_path: Path,
    journal_path: Path,
    backup_dir: Path,
) -> None:
    if not journal_path.exists():
        msg = f"no journal at {journal_path}; recovery requires either journal or backup"
        details: dict[str, object] = {
            "journal_path": str(journal_path),
            "state_path": str(state_path),
            "backup_dir": str(backup_dir),
            "reason": "no_recovery_source",
        }
        # Emit backup hint on stderr in human mode before the error envelope
        json_mode = bool(ctx.obj is not None and ctx.obj.get("json", False))
        if not json_mode:
            echo(f"Check for backups at: {backup_dir}", err=True, ctx=ctx)
        emit_error("ERR_NO_RECOVERY_SOURCE", msg, ctx=ctx, details=details)


def _dispatch_rebuild_error(
    ctx: typer.Context,
    err: Exception,
    state_path: Path,
    journal_path: Path,
    backup_dir: Path,
) -> None:
    from sdlc.errors import JournalError, StateError

    # Mutually-exclusive branches: emit_error is NoReturn, but use elif so the
    # contract is structural rather than relying on the caller's NoReturn guarantee.
    if isinstance(err, StateError):
        reason = err.details.get("reason", "")
        step = err.details.get("step", "")
        if reason == "missing_journal":
            msg = f"no journal at {journal_path}; recovery requires either journal or backup"
            emit_error(
                "ERR_NO_RECOVERY_SOURCE",
                msg,
                ctx=ctx,
                details={
                    "journal_path": str(journal_path),
                    "state_path": str(state_path),
                    "backup_dir": str(backup_dir),
                    "reason": "no_recovery_source",
                },
            )
        elif step in ("validate_journal_path", "validate_state_path"):
            # Path-validation errors share the StateError exit class but are not write failures;
            # surface them under USER_INPUT so JSON consumers can distinguish.
            emit_error(
                "ERR_USER_INPUT",
                err.message,
                ctx=ctx,
                details=dict(err.details),
            )
        else:
            # Atomic-write failures and other StateErrors: forward the inner message
            # without a "state write failed during rebuild: …" prefix, since err.message
            # already names the operation (e.g., "atomic write failed at step 5 (rename): …").
            emit_error(
                "ERR_STATE_WRITE_FAILED",
                err.message,
                ctx=ctx,
                details=dict(err.details),
            )
    elif isinstance(err, JournalError):
        step = err.details.get("step", "")
        if step == "reader_invariant":
            # journal/reader.py emits "lineno" (not "line") in details — match the producer.
            lineno = err.details.get("lineno", "?")
            prev_seq = err.details.get("prev_seq", "?")
            next_seq = err.details.get("next_seq", "?")
            emit_error(
                "ERR_JOURNAL_CORRUPT",
                f"journal corruption: monotonic_seq regression at line {lineno}"
                f" (prev_seq={prev_seq}, next_seq={next_seq}); manual intervention required",
                ctx=ctx,
                details=dict(err.details),
            )
        elif step == "project_unknown_schema":
            schema_version = err.details.get("schema_version", "?")
            emit_error(
                "ERR_JOURNAL_SCHEMA_DRIFT",
                f"journal contains entries with schema_version={schema_version};"
                f" this build expects schema_version=1;"
                f" run `sdlc migrate-v{schema_version}` after recovering"
                f" or rebuild from a journal that pre-dates the schema bump",
                ctx=ctx,
                details=dict(err.details),
            )
        elif step == "read_journal":
            # Journal-shape problems (directory / pipe / device node / permission denied) —
            # exit 2 (ERR_JOURNAL_CORRUPT) rather than exit 3 (ERR_INFRASTRUCTURE) so this
            # stays consistent with Stories 1.18-1.19 journal-error class.
            emit_error(
                "ERR_JOURNAL_CORRUPT",
                f"journal read failed during rebuild: {err.message}",
                ctx=ctx,
                details=dict(err.details),
            )
        else:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"journal read error during rebuild: {err.message}",
                ctx=ctx,
                details=dict(err.details),
            )


def _emit_success(
    ctx: typer.Context,
    entries_replayed: int,
    state_path: Path,
    journal_path: Path,
) -> None:
    if ctx.obj is not None and ctx.obj.get("json", False):
        # emit_json injects "command" via setdefault; pass payload without it to avoid
        # implying the explicit key wins (it does not — emit_json's setdefault is no-op
        # when the key is already present, but listing it twice is misleading).
        emit_json(
            "rebuild-state",
            {
                "result": "success",
                "entries_replayed": entries_replayed,
                "state_path": str(state_path),
                "journal_path": str(journal_path),
            },
            ctx=ctx,
        )
    else:
        echo(f"state rebuilt from {entries_replayed} journal entries", ctx=ctx)


def run_rebuild_state(*, ctx: typer.Context) -> None:
    """Rebuild state.json from the journal (FR35)."""
    from sdlc.errors import JournalError, StateError
    from sdlc.state.rebuild import rebuild_state_from_journal

    repo_root = _get_repo_root_or_cwd()
    state_path, journal_path, backup_dir = _resolve_paths(repo_root)

    _check_initialized_or_refuse(ctx, state_path.parent, repo_root)
    _check_recovery_source_or_refuse(ctx, state_path, journal_path, backup_dir)

    try:
        entries_replayed = rebuild_state_from_journal(
            journal_path=journal_path, state_path=state_path
        )
    except (StateError, JournalError) as err:
        _dispatch_rebuild_error(ctx, err, state_path, journal_path, backup_dir)
        return

    _emit_success(ctx, entries_replayed, state_path, journal_path)

"""`sdlc scan` implementation (FR3, Architecture §799, §1133, Decision A4 + B5).

Wraps `engine.scanner.scan` with state.json atomic write + journal scan_completed append.
Write order: state.json FIRST, then journal append (Architecture §573-§583 step 8).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import sys
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_SCAN_KIND: Final[str] = "scan_completed"
_ACTOR: Final[str] = "cli"
_STATE_TARGET_ID: Final[str] = "state"


def _compute_sha256_of_file(path: Path) -> str | None:
    """Return 'sha256:<hex>' or None if the file does not exist."""
    if not path.exists():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _now_rfc3339_utc() -> str:
    """RFC 3339 UTC with millisecond precision matching JournalEntry _RFC3339_UTC regex."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _write_state_to_disk(state, state_path: Path) -> None:  # type: ignore[no-untyped-def]
    from sdlc.state import state_to_canonical_bytes

    canonical = state_to_canonical_bytes(state)
    if sys.platform == "win32":
        _logger.warning(
            "sdlc scan on Windows uses non-atomic write fallback for state.json "
            "(POSIX-only atomic protocol unavailable). Recommended: WSL2."
        )
        state_path.write_bytes(canonical)  # noqa: state-write -- Windows non-atomic fallback; POSIX-only atomic protocol unavailable (Architecture §573)
        return
    from sdlc.state import write_state_atomic_sync  # deferred POSIX-only

    write_state_atomic_sync(state, state_path)


def _append_scan_journal_entry(
    *,
    journal_path: Path,
    seq: int,
    ts: str,
    before_hash: str | None,
    after_hash: str,
    epic_count: int,
    story_count: int,
    task_count: int,
) -> None:
    from sdlc.journal import append_sync  # deferred

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=_ACTOR,
        kind=_SCAN_KIND,
        target_id=_STATE_TARGET_ID,
        before_hash=before_hash,
        after_hash=after_hash,
        payload={
            "epic_count": epic_count,
            "story_count": story_count,
            "task_count": task_count,
        },
    )
    append_sync(entry, journal_path=journal_path)


def run_scan(*, ctx: typer.Context) -> None:
    """Refresh state.json from the artifact tree (FR3)."""
    from sdlc.errors import JournalError, StateError
    from sdlc.state import read_state, state_to_canonical_bytes

    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_PATH_REL
    journal_path = root / _JOURNAL_PATH_REL

    if not state_path.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    before_hash = _compute_sha256_of_file(state_path)

    try:
        pre_state = read_state(state_path)
    except StateError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"failed to read existing state.json: {exc}",
            ctx=ctx,
            details={"path": str(state_path)},
        )
    if pre_state is None:
        # Defensive: state_path.exists() was true above, so read_state should not return None.
        # If it does (TOCTOU file removal between checks), treat as not initialized.
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    seq = pre_state.next_monotonic_seq

    from sdlc.engine import scan as engine_scan

    try:
        scanned = engine_scan(project_root=root)
    except StateError as exc:
        emit_error(
            "ERR_SCAN_FAILED",
            f"scan failed: {exc}",
            ctx=ctx,
            details=dict(exc.details) if hasattr(exc, "details") else {},
        )

    new_state = scanned.model_copy(update={"next_monotonic_seq": seq + 1})

    canonical_bytes = state_to_canonical_bytes(new_state)
    after_hash = f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"

    try:
        _write_state_to_disk(new_state, state_path)
    except (OSError, StateError) as exc:
        emit_error(
            "ERR_STATE_WRITE_FAILED",
            f"state write failed: {exc}",
            ctx=ctx,
            details={"path": str(state_path)},
        )

    ts = _now_rfc3339_utc()
    try:
        _append_scan_journal_entry(
            journal_path=journal_path,
            seq=seq,
            ts=ts,
            before_hash=before_hash,
            after_hash=after_hash,
            epic_count=len(new_state.epics),
            story_count=len(new_state.stories),
            task_count=len(new_state.tasks),
        )
    except JournalError as exc:
        emit_error(
            "ERR_JOURNAL_APPEND_FAILED",
            f"journal append failed: {exc}",
            ctx=ctx,
            details={"path": str(journal_path), "seq": seq},
        )

    phase = getattr(new_state, "phase", 1)
    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            "scan",
            {
                "project_root": str(root),
                "phase": phase,
                "epic_count": len(new_state.epics),
                "story_count": len(new_state.stories),
                "task_count": len(new_state.tasks),
                "next_monotonic_seq": new_state.next_monotonic_seq,
                "journal_entry_seq": seq,
            },
            ctx=ctx,
        )
    else:
        echo(
            f"sdlc scan: {root} - phase {phase}, "
            f"{len(new_state.epics)} epics, {len(new_state.stories)} stories, "
            f"{len(new_state.tasks)} tasks (state.json refreshed)",
            ctx=ctx,
        )

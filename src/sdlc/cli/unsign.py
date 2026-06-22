"""sdlc unsign --mad-only — remove mad-mode signoffs and clarifications (FR23, 4.12)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors.base import SdlcError, SignoffError
from sdlc.signoff import PHASE_DIR_MAP, SignoffRecord
from sdlc.signoff.records import _signoff_path, list_records

_MAD_APPROVED_BY: Final[str] = "ai-mad-mode"
_EMPTY_MSG: Final[str] = "no mad-mode signoffs found; nothing to unsign"
_EVENT_SENTINEL: Final[str] = "sha256:" + "0" * 64
_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_CLARIFICATIONS_REL: Final[str] = ".claude/state/clarifications"
_OPEN_CLARIFICATION_NAME: Final[str] = "open_clarification.md"
_RESOLUTION_NAME: Final[str] = "resolution.md"
_ACTOR: Final[str] = "cli"
_ORIGINAL_OPEN_SECTION: Final[str] = "## Original Open Clarification"
_RESOLVED_BY_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^resolved_by:\s*(\S+)\s*$")

__all__ = (
    "_EMPTY_MSG",
    "_EVENT_SENTINEL",
    "_MAD_APPROVED_BY",
    "extract_open_body_from_resolution",
    "find_mad_resolution_dirs",
    "run_unsign",
    "select_mad_records",
)


def select_mad_records(records: tuple[SignoffRecord, ...]) -> tuple[SignoffRecord, ...]:
    """Return signoff records whose approved_by is the mad-mode actor."""
    return tuple(rec for rec in records if rec.approved_by == _MAD_APPROVED_BY)


def extract_open_body_from_resolution(resolution_text: str) -> str:
    """Recover the original open-clarification body embedded by mad-mode resolution."""
    marker = _ORIGINAL_OPEN_SECTION
    idx = resolution_text.find(marker)
    if idx < 0:
        raise ValueError(f"resolution missing {_ORIGINAL_OPEN_SECTION!r} section")
    body = resolution_text[idx + len(marker) :]
    decision_idx = body.find("\n## Decision")
    if decision_idx >= 0:
        body = body[:decision_idx]
    stripped = body.strip()
    return stripped + "\n" if stripped else ""


def _resolution_is_mad(resolution_text: str) -> bool:
    match = _RESOLVED_BY_RE.search(resolution_text)
    return match is not None and match.group(1) == _MAD_APPROVED_BY


def find_mad_resolution_dirs(clarifications_root: Path) -> tuple[Path, ...]:
    """Return clarification dirs whose resolution.md was resolved by mad-mode."""
    if not clarifications_root.is_dir():
        return ()
    found: list[Path] = []
    for child in sorted(clarifications_root.iterdir()):
        if not child.is_dir():
            continue
        resolution_path = child / _RESOLUTION_NAME
        if not resolution_path.is_file():
            continue
        try:
            text = resolution_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _resolution_is_mad(text):
            found.append(child)
    return tuple(found)


def _append_signoff_unsigned(
    *,
    journal_path: Path,
    now: str,
    removed_count: int,
    phase: int | None = None,
    clarification_id: str | None = None,
) -> None:
    from sdlc.journal import append_sync
    from sdlc.journal.writer import allocate_next_seq_for_append_sync

    payload: dict[str, object] = {
        "mad_only": True,
        "removed_count": removed_count,
    }
    if phase is not None:
        payload["phase"] = phase
    if clarification_id is not None:
        payload["clarification_id"] = clarification_id

    target_id = f"phase-{phase}" if phase is not None else f"clarification-{clarification_id}"

    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        monotonic_seq=seq,
        ts=now,
        kind="signoff_unsigned",
        actor=_ACTOR,
        target_id=target_id,
        before_hash=None,
        after_hash=_EVENT_SENTINEL,
        payload=payload,
    )
    try:
        append_sync(entry, journal_path=journal_path)
    except OSError as exc:
        raise OSError(f"journal append failed for signoff_unsigned: {exc}") from exc


def _remove_mad_signoff(*, repo_root: Path, phase: int) -> None:
    record_path = _signoff_path(phase, repo_root)
    if record_path.is_file():
        record_path.unlink()
    phase_dir = PHASE_DIR_MAP.get(phase)
    if phase_dir is not None:
        draft_path = repo_root / phase_dir / "SIGNOFF.md"
        if draft_path.is_file():
            draft_path.unlink()


def _revert_mad_clarification(*, clar_dir: Path) -> None:
    resolution_path = clar_dir / _RESOLUTION_NAME
    resolution_text = resolution_path.read_text(encoding="utf-8")
    open_body = extract_open_body_from_resolution(resolution_text)
    open_path = clar_dir / _OPEN_CLARIFICATION_NAME
    atomic_write(open_path.resolve(), open_body)
    resolution_path.unlink()


def run_unsign(  # noqa: C901
    *,
    ctx: typer.Context,
    mad_only: bool,
    include_clarifications: bool,
) -> None:
    """Remove mad-mode signoffs; optionally revert mad-resolved clarifications."""
    if not mad_only:
        emit_error(
            "ERR_USER_INPUT",
            "unsign requires --mad-only in v1; full unsign is not supported",
            ctx=ctx,
            details={"hint": "run `sdlc unsign --mad-only`"},
        )

    root = _get_repo_root_or_cwd()
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    journal_path = root / _JOURNAL_REL
    now = now_rfc3339_utc_ms()

    try:
        mad_records = select_mad_records(list_records(root))
    except SignoffError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"cannot list signoff records: {exc}",
            ctx=ctx,
        )

    clar_root = root / _CLARIFICATIONS_REL
    mad_clar_dirs = find_mad_resolution_dirs(clar_root) if include_clarifications else ()

    if not mad_records and not mad_clar_dirs:
        echo(_EMPTY_MSG, ctx=ctx)  # gated: NO-OP in --json mode (output.echo)
        emit_json(
            "unsign",
            {"removed_count": 0, "removed_phases": [], "outcome": "success"},
            ctx=ctx,
        )
        return

    signoff_removed_count = len(mad_records)
    clar_removed_count = len(mad_clar_dirs)
    total_removed = signoff_removed_count + clar_removed_count

    for record in mad_records:
        phase = record.phase
        try:
            # per-event: this entry removes exactly one phase (CR4.12-D1)
            _append_signoff_unsigned(
                journal_path=journal_path,
                now=now,
                removed_count=1,
                phase=phase,
            )
        except OSError as exc:
            emit_error(
                "ERR_JOURNAL_APPEND_FAILED",
                str(exc),
                ctx=ctx,
                details={"path": str(journal_path), "phase": phase},
            )
        try:
            _remove_mad_signoff(repo_root=root, phase=phase)
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to remove mad signoff for phase {phase}: {exc}",
                ctx=ctx,
                details={"phase": phase},
            )

    for clar_dir in mad_clar_dirs:
        clarification_id = clar_dir.name
        try:
            # per-event: this entry reverts exactly one clarification (CR4.12-D1)
            _append_signoff_unsigned(
                journal_path=journal_path,
                now=now,
                removed_count=1,
                clarification_id=clarification_id,
            )
        except OSError as exc:
            emit_error(
                "ERR_JOURNAL_APPEND_FAILED",
                str(exc),
                ctx=ctx,
                details={"path": str(journal_path), "clarification_id": clarification_id},
            )
        try:
            _revert_mad_clarification(clar_dir=clar_dir)
        except (OSError, ValueError, SdlcError) as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to revert mad clarification {clarification_id}: {exc}",
                ctx=ctx,
                details={"clarification_id": clarification_id},
            )

    removed_phases = [rec.phase for rec in mad_records]
    emit_json(
        "unsign",
        {
            "removed_count": total_removed,
            "removed_phases": removed_phases,
            "outcome": "success",
        },
        ctx=ctx,
    )

"""`sdlc scan` implementation (FR3, Architecture §799, §1133, Decision A4 + B5).

Wraps `engine.scanner.scan` with state.json atomic write + journal scan_completed append.
Write order: state.json FIRST, then journal append (Architecture §573-§583 step 8).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import sys
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._fs import sha256_file_or_none
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._signoff_check import check_signoffs as _check_signoffs  # P-extract: LOC cap
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_SCAN_KIND: Final[str] = "scan_completed"
_ACTOR: Final[str] = "cli"
_STATE_TARGET_ID: Final[str] = "state"
_PHASE_2_GATE: Final[int] = 2  # named constant to satisfy PLR2004 in _check_signoffs


def _compute_sha256_of_file(path: Path) -> str | None:
    """Return 'sha256:<hex>' or None if the file does not exist (delegates to shared helper)."""
    return sha256_file_or_none(path)


def _now_rfc3339_utc() -> str:
    """RFC 3339 UTC with millisecond precision (delegates to shared helper)."""
    return now_rfc3339_utc_ms()


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


def _evaluate_hook_trust(root: Path) -> tuple[str, int, str | None]:
    """Single detect_tampering call shared by warning emit + JSON envelope (F7).

    Returns (status, drift_count, warning_text). On any unexpected exception
    (advisory-only v1 contract per AC5), coerces to ``status="uninitialized"``
    so consumers see a documented enum value (P6).
    """
    from sdlc.hooks.tampering import detect_tampering, render_warning

    state_root = root / ".claude" / "state"
    hooks_root = root / ".claude" / "hooks"
    try:
        report = detect_tampering(state_root, hooks_root)
    except Exception as exc:  # P2: advisory-only — broaden from HookError-only
        _logger.warning("hook trust check failed (advisory): %s", exc)
        return ("uninitialized", 0, None)  # P6: coerce to documented enum

    if report.status == "clean":
        return ("clean", 0, None)

    warning = render_warning(report)
    return (report.status, len(report.drift), warning)


def _emit_trust_warning(warning: str | None) -> None:
    """Emit warning to stderr exactly once (P11)."""
    if warning is None:
        return
    # P11: pick stderr via typer.echo (the user-facing channel). Drop the
    # parallel _logger.warning call that produced duplicate output when the
    # logger handler was also stderr.
    # P22: BrokenPipeError on closed-stderr (e.g. piped to `head`) must not
    # crash a successful scan post-state.json-commit.
    with contextlib.suppress(BrokenPipeError, OSError):
        typer.echo(warning, err=True)


def run_scan(*, ctx: typer.Context) -> None:
    """Refresh state.json from the artifact tree (FR3)."""
    from sdlc.errors import JournalError, StateError
    from sdlc.state import read_state_or_recover, state_to_canonical_bytes

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

    # ADR-023 mandates callers pass canonical resolved paths to read_state_or_recover so the
    # recovery prompt names a stable absolute path. Resolve both — symmetric with journal_path.
    try:
        pre_state = read_state_or_recover(state_path.resolve(), journal_path.resolve())
    except StateError as exc:
        emit_error(
            "ERR_STATE_MALFORMED",
            exc.message,
            ctx=ctx,
            details=dict(exc.details),
        )
    if pre_state is None:
        # TOCTOU: state_path existed above but vanished before the read. Treat as not initialized.
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Use max(state seq, journal seq + 1) so commands that append to the
    # journal without updating state.json (e.g. `sdlc signoff`) don't cause
    # a monotonic_seq regression here (same pattern as cli/epics.py:301).
    from sdlc.journal._seq import _read_highest_seq

    journal_highest = _read_highest_seq(journal_path.resolve())
    seq = max(pre_state.next_monotonic_seq, journal_highest + 1)

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

    # --- Signoff check pass (AC5, AC6, Story 2A.12 — non-blocking) ---
    # P2: capture per-phase signoff state report for emit_json envelope (AC6 third-And).
    signoffs_report = _check_signoffs(root, journal_path, ctx=ctx)

    # --- Hook tampering detection (FR39, NFR-SEC-5, AC5, AC7 — advisory-only v1) ---
    # F7: single detect_tampering call shared by stderr warning + --json envelope
    # so they cannot disagree under TOCTOU between two separate calls.
    trust_status, trust_drift_count, trust_warning = _evaluate_hook_trust(root)
    _emit_trust_warning(trust_warning)

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
                "trust_state": {"status": trust_status, "drift_count": trust_drift_count},
                # P2 (Story 2A.12 AC6 third-And): per-phase signoff state in scan output.
                "signoffs": signoffs_report,
            },
            ctx=ctx,
        )
    else:
        signoff_summary = (
            ", ".join(f"phase-{s['phase']}: {s['state']}" for s in signoffs_report)
            if signoffs_report
            else "no-signoff-check"
        )
        echo(
            f"sdlc scan: {root} - phase {phase}, "
            f"{len(new_state.epics)} epics, {len(new_state.stories)} stories, "
            f"{len(new_state.tasks)} tasks (state.json refreshed); "
            f"signoffs: {signoff_summary}",
            ctx=ctx,
        )

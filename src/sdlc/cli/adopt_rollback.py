"""`sdlc adopt-rollback` — remove adopted symlinks with orphan-signoff guard (Story 3.5)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.errors import AdoptError, JournalError, SignoffError, WorkflowError

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_ACTOR: Final[str] = "cli"
_TARGET_ID_ADOPT: Final[str] = "adopt"
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64
_KIND_ROLLBACK_STARTED: Final[str] = "adopt_rollback_started"
_FORCE_REASON: Final[str] = "invalidated by adopt rollback"
_ORPHAN_MSG: Final[str] = "rollback would orphan signoff phase-{phase}; replan first or use --force"


def _targets_for_rollback(
    root: Path,
    *,
    rollback_all: bool,
    target: str | None,
) -> list[str] | None:
    from sdlc.cli._adopted_targets import load_adopted_targets

    adopted = load_adopted_targets(root)
    if rollback_all:
        return None
    assert target is not None
    if target not in adopted:
        raise AdoptError(
            "rollback target is not in adopted-symlinks manifest",
            details={"target": target},
        )
    return [target]


def _phases_orphaned_by_rollback(
    root: Path,
    targets: list[str],
    *,
    ctx: typer.Context,
) -> list[int]:
    from sdlc.engine.replan import resolve_scope_phase
    from sdlc.signoff.states import SignoffState, compute_state

    phases: set[int] = set()
    for scope in targets:
        try:
            phase = resolve_scope_phase(scope)
        except WorkflowError:
            continue
        try:
            state = compute_state(phase, repo_root=root)
        except SignoffError as exc:
            # A malformed canonical record / SIGNOFF.md draft makes compute_state raise;
            # surface it as an envelope instead of leaking a raw traceback (fail-closed:
            # the orphan check runs before any mutation, so nothing is half-done here).
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to read signoff state for phase {phase}: {exc}",
                ctx=ctx,
                details={"phase": phase, "scope": scope},
            )
        if state == SignoffState.APPROVED:
            phases.add(phase)
    return sorted(phases)


def _invalidate_phases(
    root: Path,
    phases: list[int],
    *,
    journal_path: Path,
    now: str,
    ctx: typer.Context,
) -> None:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync
    from sdlc.journal.writer import allocate_next_seq_for_append_sync
    from sdlc.signoff.records import _signoff_path, invalidate_record

    for phase in phases:
        try:
            inv_record = invalidate_record(
                phase,
                repo_root=root,
                reason=_FORCE_REASON,
                now_utc=now,
            )
        except (SignoffError, OSError) as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to invalidate phase {phase} signoff: {exc}",
                ctx=ctx,
                details={"phase": phase},
            )

        signoff_file = _signoff_path(phase, root)
        try:
            signoff_bytes = signoff_file.read_bytes()
        except OSError as exc:
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to read phase {phase} signoff after invalidation: {exc}",
                ctx=ctx,
                details={"phase": phase},
            )
        signoff_hash = f"sha256:{hashlib.sha256(signoff_bytes).hexdigest()}"
        seq = allocate_next_seq_for_append_sync(journal_path)
        entry = JournalEntry(
            monotonic_seq=seq,
            ts=now,
            kind="signoff_invalidated",
            actor=_ACTOR,
            target_id=f"phase-{phase}",
            before_hash=None,
            after_hash=signoff_hash,
            payload={
                "phase": phase,
                "reason": _FORCE_REASON,
                "invalidated_at": inv_record.invalidated_at,
            },
        )
        try:
            append_sync(entry, journal_path=journal_path)
        except (OSError, JournalError) as exc:
            # append_sync raises JournalError (not OSError) for lock/IO failures — catch both
            # so a failed append surfaces an envelope instead of a raw traceback.
            emit_error(
                "ERR_JOURNAL_APPEND_FAILED",
                f"journal append failed for signoff_invalidated phase {phase}: {exc}",
                ctx=ctx,
                details={"path": str(journal_path), "phase": phase},
            )


def _append_rollback_intent(
    journal_path: Path,
    *,
    targets: list[str],
    phases: list[int],
    now: str,
    ctx: typer.Context,
) -> None:
    """Journal a leading intent anchor before ``--force`` signoff invalidation.

    Mirrors ``replan_cmd.run_replan`` (``replan_invalidated`` is appended first): the audit
    chain records the rollback intent + the phases about to be invalidated BEFORE any
    destructive ``invalidate_record`` / symlink unlink, so a later failure still leaves the
    intent in the journal (fail-loud posture).
    """
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync
    from sdlc.journal.writer import allocate_next_seq_for_append_sync

    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        monotonic_seq=seq,
        ts=now,
        kind=_KIND_ROLLBACK_STARTED,
        actor=_ACTOR,
        target_id=_TARGET_ID_ADOPT,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload={
            "targets": targets,
            "orphaned_phases": phases,
            "reason": _FORCE_REASON,
        },
    )
    try:
        append_sync(entry, journal_path=journal_path)
    except (OSError, JournalError) as exc:
        emit_error(
            "ERR_JOURNAL_APPEND_FAILED",
            f"journal append failed for adopt_rollback_started: {exc}",
            ctx=ctx,
            details={"path": str(journal_path)},
        )


def run_adopt_rollback(  # noqa: C901
    *,
    ctx: typer.Context,
    rollback_all: bool,
    target: str | None,
    force: bool,
) -> None:
    """Roll back one or all adopted symlinks; refuse when that would orphan an APPROVED signoff."""
    root = _get_repo_root_or_cwd()
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    journal_path = root / _JOURNAL_REL

    try:
        selected = _targets_for_rollback(root, rollback_all=rollback_all, target=target)
    except AdoptError as exc:
        emit_error("ERR_ADOPT", exc.message, ctx=ctx, details=dict(exc.details))

    scope_targets: list[str]
    if selected is None:
        from sdlc.cli._adopted_targets import load_adopted_targets

        scope_targets = sorted(load_adopted_targets(root))
    else:
        scope_targets = list(selected)

    orphaned = _phases_orphaned_by_rollback(root, scope_targets, ctx=ctx)
    if orphaned and not force:
        phase = orphaned[0]
        emit_error(
            "ERR_ADOPT",
            _ORPHAN_MSG.format(phase=phase),
            ctx=ctx,
            details={"phase": phase, "orphaned_phases": orphaned},
        )

    if orphaned and force:
        now = now_rfc3339_utc_ms()
        # Audit-anchor first (mirror replan_cmd): record rollback intent + the phases about
        # to be invalidated BEFORE any destructive invalidate_record, so a later failure
        # still leaves the intent recorded in the journal.
        _append_rollback_intent(
            journal_path,
            targets=scope_targets,
            phases=orphaned,
            now=now,
            ctx=ctx,
        )
        _invalidate_phases(
            root,
            orphaned,
            journal_path=journal_path,
            now=now,
            ctx=ctx,
        )

    def _warn(message: str) -> None:
        echo(f"  {message}", err=True, ctx=ctx)

    from sdlc.adopt.rollback import rollback as _rollback_core

    try:
        result = _rollback_core(
            root,
            targets=selected,
            journal_path=journal_path,
            warn=_warn,
        )
    except JournalError as exc:
        emit_error(
            "ERR_ADOPT",
            f"adopt rollback journal append failed: {exc}",
            ctx=ctx,
            details={"path": str(journal_path)},
        )
    except AdoptError as exc:
        emit_error("ERR_ADOPT", exc.message, ctx=ctx, details=dict(exc.details))

    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            "adopt-rollback",
            {
                "project_root": str(root),
                "removed_targets": list(result.removed_targets),
                "invalidated_phases": orphaned if force else [],
            },
            ctx=ctx,
        )
        return

    echo(f"Rolled back {len(result.removed_targets)} adopted symlink(s) in {root}", ctx=ctx)
    for t in result.removed_targets:
        echo(f"  removed: {t}", ctx=ctx)

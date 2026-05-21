"""`sdlc replan --scope=<scope>` — mark stale + invalidate downstream signoffs (FR4, 2A.19).

AC9 ordering (run_replan):
  1. Resolve repo_root; init guard → ERR_NOT_INITIALIZED
  2. Validate scope (safe POSIX path); resolve scope_phase; verify artifact exists
  3. compute_downstream → (downstream_artifacts, downstream_count)
  4. plan_invalidations → list of APPROVED phases >= scope_phase
  5. Journal replan_invalidated FIRST (preserves audit chain even if later steps fail)
  6. Per-phase: invalidate_record + journal signoff_invalidated
  7. emit_json success envelope

No workflow YAML, no specialist — pure state machinery like sdlc scan / sdlc rebuild-state.
LOC target: ≤ 320.
"""

from __future__ import annotations

import hashlib
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.engine.replan import compute_downstream, plan_invalidations, resolve_scope_phase
from sdlc.errors.base import SignoffError, WorkflowError
from sdlc.signoff.records import _is_safe_repo_relative_posix, invalidate_record

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_ACTOR: Final[str] = "cli"
_DEFAULT_REASON: Final[str] = "invalidated by replan"


def run_replan(*, ctx: typer.Context, scope: str) -> None:  # noqa: C901
    """Mark artifact and downstream stale; invalidate downstream signoffs (FR4)."""
    from sdlc.journal import append_sync  # deferred per Architecture §488
    from sdlc.journal.writer import allocate_next_seq_for_append_sync

    # Step 1 — resolve repo root + init guard (AC1)
    root = _get_repo_root_or_cwd()
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Step 2a — validate scope is a safe repo-relative POSIX path (AC1)
    if not _is_safe_repo_relative_posix(scope):
        emit_error(
            "ERR_USER_INPUT",
            f"invalid --scope: {scope}; expected a repo-relative POSIX path",
            ctx=ctx,
            details={"scope": scope},
        )

    # Step 2b — resolve scope phase (AC1)
    try:
        scope_phase = resolve_scope_phase(scope)
    except WorkflowError as exc:
        emit_error(
            "ERR_USER_INPUT",
            exc.message,
            ctx=ctx,
            details=dict(exc.details),
        )

    # Step 2c — verify the artifact exists on disk (AC1)
    abs_scope = root / scope
    if not abs_scope.exists():
        emit_error(
            "ERR_USER_INPUT",
            f"replan scope not found: {scope}; expected at {abs_scope}",
            ctx=ctx,
            details={"scope": scope, "abs_path": str(abs_scope)},
        )
    # A directory-valued scope passes resolve_scope_phase + .exists(); reject it
    # here so read_bytes() below cannot raise an uncaught IsADirectoryError.
    if not abs_scope.is_file():
        emit_error(
            "ERR_USER_INPUT",
            f"replan scope is not a file: {scope}; expected a path to an artifact file",
            ctx=ctx,
            details={"scope": scope, "abs_path": str(abs_scope)},
        )

    # Step 3 — compute downstream (AC2/D1 phase-based)
    downstream_artifacts, downstream_count = compute_downstream(root, scope_phase)

    # Step 4 — plan which phases to invalidate (AC3)
    try:
        phases_to_invalidate = plan_invalidations(root, scope_phase)
    except SignoffError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"cannot determine phases to invalidate: {exc}",
            ctx=ctx,
            details={"scope": scope},
        )

    journal_path = root / _JOURNAL_REL
    now = now_rfc3339_utc_ms()

    # Hash the scope artifact for after_hash (anchors event to scope version)
    scope_hash = f"sha256:{hashlib.sha256(abs_scope.read_bytes()).hexdigest()}"

    # Step 5 — append replan_invalidated FIRST (AC4 #1 + AC9 ordering)
    # Appended before any invalidate_record call so the audit chain records the
    # intent even if a later invalidate_record raises (fail-loud posture).
    seq = allocate_next_seq_for_append_sync(journal_path)
    replan_entry = JournalEntry(
        monotonic_seq=seq,
        ts=now,
        kind="replan_invalidated",
        actor=_ACTOR,
        target_id=scope,
        before_hash=None,
        after_hash=scope_hash,
        payload={
            "scope": scope,
            "scope_phase": scope_phase,
            "downstream_artifacts": downstream_artifacts,
            "downstream_count": downstream_count,
            "reason": _DEFAULT_REASON,
        },
    )
    try:
        append_sync(replan_entry, journal_path=journal_path)
    except OSError as exc:
        emit_error(
            "ERR_JOURNAL_APPEND_FAILED",
            f"journal append failed for replan_invalidated: {exc}",
            ctx=ctx,
            details={"path": str(journal_path)},
        )

    # Step 6 — per-phase invalidation + signoff_invalidated journal entry (AC3 + AC4 #2)
    invalidated_phases: list[int] = []
    for phase in phases_to_invalidate:
        try:
            inv_record = invalidate_record(
                phase,
                repo_root=root,
                reason=_DEFAULT_REASON,
                now_utc=now,
            )
        except (SignoffError, OSError) as exc:
            # invalidate_record failures are infrastructure / data-integrity
            # faults (bad record, disk write error) — not user input.
            emit_error(
                "ERR_INFRASTRUCTURE",
                f"failed to invalidate phase {phase} signoff: {exc}",
                ctx=ctx,
                details={"phase": phase},
            )

        invalidated_phases.append(phase)

        # Hash the invalidated signoff YAML for after_hash
        from sdlc.signoff.records import _signoff_path

        signoff_file = _signoff_path(phase, root)
        signoff_hash = f"sha256:{hashlib.sha256(signoff_file.read_bytes()).hexdigest()}"

        seq2 = allocate_next_seq_for_append_sync(journal_path)
        si_entry = JournalEntry(
            monotonic_seq=seq2,
            ts=now,
            kind="signoff_invalidated",
            actor=_ACTOR,
            target_id=f"phase-{phase}",
            before_hash=None,
            after_hash=signoff_hash,
            payload={
                "phase": phase,
                "reason": _DEFAULT_REASON,
                "invalidated_at": inv_record.invalidated_at,
            },
        )
        try:
            append_sync(si_entry, journal_path=journal_path)
        except OSError as exc:
            emit_error(
                "ERR_JOURNAL_APPEND_FAILED",
                f"journal append failed for signoff_invalidated phase {phase}: {exc}",
                ctx=ctx,
                details={"path": str(journal_path), "phase": phase},
            )

    # Step 7 — emit success JSON envelope (AC4)
    emit_json(
        "replan",
        {
            "scope": scope,
            "scope_phase": scope_phase,
            "downstream_count": downstream_count,
            "invalidated_phases": invalidated_phases,
            "outcome": "success",
        },
        ctx=ctx,
    )

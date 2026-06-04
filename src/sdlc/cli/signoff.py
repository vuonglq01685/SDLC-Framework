"""`sdlc signoff <phase>` — Phase signoff draft generation (FR11, Story 2A.12).

Decision AC1/D1: generate SIGNOFF.md mechanically (no AI dispatch). See signoff/generator.py.
Decision AC3/D2 (re-decided 2026-05-14 per code-review DR3): hook chain is bypassed for the
SIGNOFF.md write — phase_gate.py:137's unconditional "01-" prefix allow incidentally covers
the write. True intent-aware D1 deferred as ``EPIC-2A-DEBT-SIGNOFF-WRITE-INTENT``.

LOC target: ≤ 200.
"""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._time import now_rfc3339_utc_ms
from sdlc.cli.output import emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.signoff import SignoffState, compute_state

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_ACTOR: Final[str] = "cli"
_VALID_PHASES: Final[frozenset[int]] = frozenset({1, 2})
# P20: MappingProxyType for read-only contract (was: plain Final[dict] — mutable at runtime).
_PHASE_DIRS: Final[MappingProxyType[int, str]] = MappingProxyType(
    {1: "01-Requirement", 2: "02-Architecture"}
)
_PHASE_2: Final[int] = 2  # named constant to satisfy PLR2004


def run_signoff(*, ctx: typer.Context, phase: int) -> None:  # noqa: C901
    """Generate a phase signoff draft (FR11, AC8)."""
    from sdlc.errors import SignoffError
    from sdlc.journal import append_sync
    from sdlc.journal.writer import allocate_next_seq_for_append_sync
    from sdlc.signoff.generator import generate_signoff_md

    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_REL
    journal_path = root / _JOURNAL_REL

    # Pre-flight: project initialized
    if not state_path.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Pre-flight: valid phase
    if phase not in _VALID_PHASES:
        emit_error(
            "ERR_USER_INPUT",
            f"invalid phase {phase}; must be 1 or 2",
            ctx=ctx,
            details={"phase": phase},
        )

    phase_dir_name = _PHASE_DIRS[phase]

    # Pre-flight: phase 2 requires phase 1 APPROVED.
    # P14: emit_error is NoReturn (see output.py), but assigning the
    # compute_state result inside try/except + reading it after the except
    # branch is brittle to refactor (mypy doesn't flag unbound-locals when the
    # except calls a NoReturn). Refactor to inline both pre-flight checks
    # without a fall-through variable read.
    if phase == _PHASE_2:
        try:
            phase1_state = compute_state(1, repo_root=root)
        except SignoffError as exc:
            # P14: emit_error is typed NoReturn (output.py) — mypy treats the
            # subsequent `phase1_state` read as reachable only when this branch
            # is NOT taken, so no fall-through return needed.
            emit_error(
                "ERR_PHASE1_NOT_APPROVED",
                f"phase 1 signoff state could not be read: {exc}",
                ctx=ctx,
                details={"phase": 1},
            )
        if phase1_state != SignoffState.APPROVED:
            emit_error(
                "ERR_PHASE1_NOT_APPROVED",
                "phase 1 signoff must be APPROVED before generating phase 2 signoff draft; "
                "run '/sdlc-signoff 1' first",
                ctx=ctx,
                details={"phase1_state": str(phase1_state)},
            )

    # Pre-flight: current phase state — refuse if already APPROVED
    try:
        current_state = compute_state(phase, repo_root=root)
    except SignoffError as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"could not read signoff state for phase {phase}: {exc}",
            ctx=ctx,
            details={"phase": phase},
        )

    if current_state == SignoffState.APPROVED:
        emit_error(
            f"ERR_PHASE{phase}_ALREADY_APPROVED",
            f"phase {phase} signoff is already APPROVED; "
            f"use 'sdlc replan --scope={phase_dir_name}/' "
            "to invalidate before regenerating the draft",
            ctx=ctx,
            details={"phase": phase, "state": str(current_state)},
        )

    # Generate SIGNOFF.md (P10: returns (path, artifact_count) tuple).
    try:
        from sdlc.cli._adopted_targets import load_adopted_target_sources

        signoff_path, artifact_count = generate_signoff_md(
            phase, repo_root=root, adopted_sources=load_adopted_target_sources(root)
        )
    except SignoffError as exc:
        # Map error code from exc.details["code"] if present (P3 cleanup);
        # otherwise default to ERR_NO_ARTIFACTS for backwards compat.
        code = (
            str(exc.details.get("code", "ERR_NO_ARTIFACTS"))
            if isinstance(exc.details, dict)
            else "ERR_NO_ARTIFACTS"
        )
        emit_error(
            code,
            str(exc.message),
            ctx=ctx,
            details=dict(exc.details) if exc.details else {},
        )

    now = now_rfc3339_utc_ms()

    # Journal: signoff_draft_generated.
    # P5: use canonical seq allocator (holds flock + reads max seq, not last-line).
    # P6: journal append failure surfaces ERR_JOURNAL_APPEND_FAILED (was: silent
    # `except Exception: pass` hiding audit-chain gaps).
    after_hash = f"sha256:{hashlib.sha256(signoff_path.read_bytes()).hexdigest()}"
    try:
        seq = allocate_next_seq_for_append_sync(journal_path)
        entry = JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=now,
            actor=_ACTOR,
            kind="signoff_draft_generated",
            target_id=f"signoff-phase-{phase}",
            before_hash=None,
            after_hash=after_hash,
            payload={
                "phase": phase,
                "artifact_count": artifact_count,
                "actor": "cli",
            },
        )
        append_sync(entry, journal_path=journal_path)
    except OSError as exc:
        emit_error(
            "ERR_JOURNAL_APPEND_FAILED",
            f"journal append failed for signoff_draft_generated phase {phase}: {exc}",
            ctx=ctx,
            details={"path": str(journal_path), "phase": phase},
        )

    emit_json(
        "signoff",
        {
            "phase": phase,
            "signoff_path": str(signoff_path.relative_to(root)),
            "artifact_count": artifact_count,
            "outcome": "success",
            "next_step": (
                f"edit {signoff_path.relative_to(root)} and set approved: true, "
                "then run 'sdlc scan'"
            ),
        },
        ctx=ctx,
    )

"""Mad-mode auto-resolution for resolvable STOP triggers (Story 4.11, FR20/FR23)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Final

from sdlc.concurrency.io_primitives import atomic_write
from sdlc.engine.stop_triggers import StopDecision, check_stop
from sdlc.errors import SignoffError
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import JournalEntry, append_with_seq_alloc
from sdlc.signoff import (
    PHASE_DIR_MAP,
    SignoffState,
    compute_state,
    generate_signoff_md,
    validate_signoff,
    write_record,
)
from sdlc.signoff.hasher import compute_signoff_record_hash
from sdlc.state.model import State

log = logging.getLogger(__name__)

_ACTOR: Final[str] = "auto_mad"
_APPROVED_BY: Final[str] = "ai-mad-mode"
_EVENT_SENTINEL: Final[str] = "sha256:" + "0" * 64
_OPEN_CLARIFICATION_NAME: Final[str] = "open_clarification.md"
_OPTIONS_NAME: Final[str] = "options.md"
_RESOLUTION_NAME: Final[str] = "resolution.md"
_SYNTH_PICK_SENTINEL: Final[str] = "synth-pick"
_RESOLVABLE_TRIGGERS: Final[frozenset[str]] = frozenset({"open_clarification", "signoff_required"})
_OPTION_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^## Option \d+:")


def extract_first_option(options_text: str) -> str | None:
    """Return the body of the first ``## Option N:`` section, or None if absent."""
    matches = list(_OPTION_HEADER_RE.finditer(options_text))
    if not matches:
        return None
    start = matches[0].end()
    end = matches[1].start() if len(matches) > 1 else len(options_text)
    body = options_text[start:end].strip()
    return body or None


def _phase_from_signoff_target(target: str) -> int:
    dir_name = target.split("/", maxsplit=1)[0]
    for phase, phase_dir in PHASE_DIR_MAP.items():
        if phase_dir == dir_name:
            return phase
    raise ValueError(f"cannot derive phase from signoff target {target!r}")


def _patch_signoff_draft_for_mad(content: str, *, approved_by: str, approved_at: str) -> str:
    patched = re.sub(r"(?m)^approved:\s*false\s*$", "approved: true", content, count=1)
    patched = re.sub(
        r"(?m)^approved_by:\s*null\s*$",
        f"approved_by: {approved_by}",
        patched,
        count=1,
    )
    patched = re.sub(
        r"(?m)^approved_at:\s*null\s*$", f"approved_at: {approved_at}", patched, count=1
    )
    return patched


async def _journal_auto_mad_resolve(
    journal_path: Path,
    *,
    target: str,
    decision: str,
    correlation_id: str,
) -> None:
    await append_with_seq_alloc(
        journal_path,
        lambda seq: JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=now_rfc3339_utc_ms(),
            actor=_ACTOR,
            kind="auto_mad_resolve",
            target_id=target,
            before_hash=None,
            after_hash=_EVENT_SENTINEL,
            payload={
                "target": target,
                "decision": decision,
                "correlation_id": correlation_id,
            },
        ),
    )


async def _journal_signoff_recorded(
    journal_path: Path,
    *,
    phase: int,
    approved_by: str,
    artifact_count: int,
    record_hash: str,
) -> None:
    await append_with_seq_alloc(
        journal_path,
        lambda seq: JournalEntry(
            schema_version=1,
            monotonic_seq=seq,
            ts=now_rfc3339_utc_ms(),
            actor=_ACTOR,
            kind="signoff_recorded",
            target_id=f"signoff-phase-{phase}",
            before_hash=None,
            after_hash=record_hash,
            payload={
                "phase": phase,
                "approved_by": approved_by,
                "artifact_count": artifact_count,
                "all_hashes_clean": True,
            },
        ),
    )


async def mad_sign_phase(
    repo_root: Path,
    *,
    stop: StopDecision,
    journal_path: Path,
    correlation_id: str,
    now_utc: str,
) -> None:
    """Seed/patch SIGNOFF.md and run validate→write→journal (D1a)."""
    if stop.target is None:
        raise ValueError("signoff_required stop missing target")
    phase = _phase_from_signoff_target(stop.target)
    draft_path = repo_root / stop.target

    state = compute_state(phase=phase, repo_root=repo_root)
    if state == SignoffState.AWAITING_SIGNOFF:
        generate_signoff_md(phase, repo_root=repo_root)

    if not draft_path.is_file():
        raise FileNotFoundError(f"SIGNOFF.md missing after mad-sign seed: {draft_path}")

    original = draft_path.read_text(encoding="utf-8")
    patched = _patch_signoff_draft_for_mad(original, approved_by=_APPROVED_BY, approved_at=now_utc)
    await asyncio.to_thread(atomic_write, draft_path.resolve(), patched)

    validated = validate_signoff(phase, repo_root=repo_root, now_utc=now_utc)
    record_hash = compute_signoff_record_hash(validated.record)
    # Journal BEFORE write_record (the un-fire): write_record makes compute_state→APPROVED,
    # which stops signoff_required from re-firing. Journaling first guarantees that if the
    # STOP ever stops firing, the audit entry already exists; a journal failure leaves the
    # record unwritten so the STOP re-fires and the resolve retries idempotently (D1 review).
    await _journal_signoff_recorded(
        journal_path,
        phase=phase,
        approved_by=validated.record.approved_by,
        artifact_count=len(validated.record.artifacts),
        record_hash=record_hash,
    )
    await _journal_auto_mad_resolve(
        journal_path,
        target=stop.target,
        decision=f"ai-mad-mode signoff phase {phase}",
        correlation_id=correlation_id,
    )
    write_record(validated.record, repo_root=repo_root)


def _build_resolution_body(
    *,
    clarification_id: str,
    decision: str,
    resolved_at: str,
    open_body: str,
    option_text: str | None,
) -> str:
    option_section = option_text if option_text is not None else decision
    return (
        f"# Mad-Mode Resolution\n\n"
        f"resolved_by: {_APPROVED_BY}\n"
        f"clarification_id: {clarification_id}\n"
        f"resolved_at: {resolved_at}\n"
        f"decision: {decision}\n\n"
        f"## Original Open Clarification\n\n"
        f"{open_body.strip()}\n\n"
        f"## Decision\n\n"
        f"{option_section.strip()}\n"
    )


def _rel_to_repo(path: Path, repo_root: Path) -> str:
    """Best-effort repo-relative string; never raises on a repo_root form/symlink mismatch."""
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return os.path.relpath(path, repo_root)


async def resolve_clarification(
    repo_root: Path,
    *,
    stop: StopDecision,
    journal_path: Path,
    correlation_id: str,
    now_utc: str,
) -> None:
    """Read option 1, write resolution artifact, remove open_clarification.md (C6/C7)."""
    if stop.target is None:
        raise ValueError("open_clarification stop missing target")
    open_path = Path(stop.target)
    if not open_path.is_file():
        open_path = repo_root / stop.target
    clar_dir = open_path.parent
    clarification_id = clar_dir.name
    open_body = open_path.read_text(encoding="utf-8")

    options_path = clar_dir / _OPTIONS_NAME
    if options_path.is_file():
        decision = extract_first_option(options_path.read_text(encoding="utf-8"))
        if decision is None:
            decision = _SYNTH_PICK_SENTINEL
        option_text = decision
    else:
        decision = _SYNTH_PICK_SENTINEL
        option_text = None

    resolution_path = clar_dir / _RESOLUTION_NAME
    resolution_body = _build_resolution_body(
        clarification_id=clarification_id,
        decision=decision,
        resolved_at=now_utc,
        open_body=open_body,
        option_text=option_text,
    )
    # Resolve the audit target up-front (before any disk mutation) so it can never raise
    # mid-sequence after the un-fire (D1 review fix).
    rel_target = _rel_to_repo(clar_dir, repo_root)
    await asyncio.to_thread(atomic_write, resolution_path.resolve(), resolution_body)
    # Journal BEFORE unlinking open_clarification.md (the only action that un-fires the STOP):
    # a journal failure leaves the STOP firing, so resume retries idempotently instead of
    # silently dropping the audit entry (D1 review fix).
    await _journal_auto_mad_resolve(
        journal_path,
        target=rel_target,
        decision=decision,
        correlation_id=correlation_id,
    )
    await asyncio.to_thread(open_path.unlink)


_MAD_CONTINUE = object()


async def resolve_stop_after_dispatch(
    *,
    repo_root: Path,
    state: State,
    journal_path: Path,
    state_path: Path | None,
    iteration_seq: int,
    correlation_id: str,
    mad_mode: bool,
    rebuild_state: Callable[[Path, Path], Awaitable[None]],
    finish_halted: Callable[..., Awaitable[Any]],
) -> Any:
    """Return halt result, ``mad_continue_sentinel`` after mad-resolve, or None when no STOP."""
    stop = check_stop(repo_root=repo_root, state=state)
    if not stop.fired:
        return None
    if await try_mad_resolve_stop_and_continue(
        repo_root=repo_root,
        stop=stop,
        journal_path=journal_path,
        state_path=state_path,
        correlation_id=correlation_id,
        mad_mode=mad_mode,
        rebuild_state=rebuild_state,
    ):
        return _MAD_CONTINUE
    return await finish_halted(
        journal_path=journal_path,
        state_path=state_path,
        iteration_seq=iteration_seq,
        correlation_id=correlation_id,
        stop=stop,
        last_action="dispatch",
    )


async def try_mad_resolve_stop_and_continue(
    *,
    repo_root: Path,
    stop: StopDecision,
    journal_path: Path,
    state_path: Path | None,
    correlation_id: str,
    mad_mode: bool,
    rebuild_state: Callable[[Path, Path], Awaitable[None]],
) -> bool:
    """Resolve a mad-eligible STOP and rebuild state; return True to continue the loop."""
    if not mad_mode or not stop.fired or stop.trigger not in _RESOLVABLE_TRIGGERS:
        return False
    if not await maybe_mad_resolve_stop(
        repo_root,
        stop=stop,
        journal_path=journal_path,
        correlation_id=correlation_id,
    ):
        return False
    if state_path is not None:
        await rebuild_state(journal_path, state_path)
    return True


async def maybe_mad_resolve_stop(
    repo_root: Path,
    *,
    stop: StopDecision,
    journal_path: Path,
    correlation_id: str,
) -> bool:
    """Resolve a mad-eligible STOP; return True when resolved (loop should continue)."""
    if not stop.fired or stop.trigger not in _RESOLVABLE_TRIGGERS:
        return False

    now_utc = now_rfc3339_utc_ms()
    try:
        if stop.trigger == "signoff_required":
            await mad_sign_phase(
                repo_root,
                stop=stop,
                journal_path=journal_path,
                correlation_id=correlation_id,
                now_utc=now_utc,
            )
        elif stop.trigger == "open_clarification":
            await resolve_clarification(
                repo_root,
                stop=stop,
                journal_path=journal_path,
                correlation_id=correlation_id,
                now_utc=now_utc,
            )
        else:
            return False
    except (OSError, ValueError, SignoffError) as exc:
        # SignoffError (⊂ SdlcError) is raised by validate_signoff on artifact hash drift /
        # an un-patchable draft; catching it here halts the loop gracefully via finish_halted
        # instead of crashing run_auto_loop with an uncaught exception (P1 review fix).
        log.warning("mad_resolve_failed trigger=%s error=%s", stop.trigger, exc)
        return False

    return True

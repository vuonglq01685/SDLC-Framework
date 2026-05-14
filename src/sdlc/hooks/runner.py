"""Hook runner: HookDecision + run_hook_chain (AC3, AC6, Story 2A.4).

Architecture §363 (Decision D1): declaration-order sequential execution.
Architecture §364 (Decision D2): one HookPayload contract, two callers.
Architecture §1109: hooks/ does NOT import engine/ or dispatcher/.

Bypass policy (AC6, NFR-SEC-4):
- naming_validator is NEVER bypassed.
- phase_gate bypass is per-dispatch, NOT per-session.
- bypass appends kind=bypass_signoff journal entry when the gate would have denied.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import HookError
from sdlc.ids.clock import now_rfc3339_utc_ms

_GIT_TIMEOUT_SECONDS: Final[float] = 5.0
_BYPASS_MIN_JUSTIFICATION_LEN: Final[int] = 10
_BYPASS_MAX_JUSTIFICATION_LEN: Final[int] = 500

# Sentinel used to detect that phase_gate was bypassed for a gated path.
_BYPASS_APPLIED_KIND: Final[str] = "bypass_signoff"
_HOOK_REJECTED_KIND: Final[str] = "hook_rejected"


@dataclass(frozen=True)
class HookDecision:
    """Runtime-only result of a hook chain execution (NOT a wire-format contract).

    decision: "allow" → write proceeds; "deny" → write blocked.
    hook_name: populated on deny; None for chain-level allow.
    reason: human-readable; required when decision == "deny".
    error_code: one of {naming_violation, phase_gate_violation,
        trust_uninitialized, trust_corrupted, hook_internal_error}; None for allow.
    """

    decision: Literal["allow", "deny"]
    hook_name: str | None
    reason: str | None
    error_code: str | None

    @classmethod
    def allow(cls) -> HookDecision:
        return cls(decision="allow", hook_name=None, reason=None, error_code=None)

    @classmethod
    def deny(cls, *, hook_name: str, reason: str, error_code: str) -> HookDecision:
        return cls(
            decision="deny",
            hook_name=hook_name,
            reason=reason,
            error_code=error_code,
        )


@dataclass(frozen=True)
class BypassRequest:
    """Bypass parameters propagated from dispatcher callers to run_hook_chain (AC6, Story 2A.6).

    bypass_phase_gate: when True, phase_gate is skipped for Phase 2/3 paths.
    justification: required when bypass_phase_gate=True (min 10 chars).

    Canonical creation entry point is ``cli/_bypass.py:validate_bypass_request`` —
    it adds trust-store checks on top of the length validation here. This dataclass
    is also defensively self-validating so callers cannot construct an invalid
    instance and only fail later inside ``run_hook_chain`` (DR5 → D1 fix).
    """

    bypass_phase_gate: bool = False
    justification: str | None = None

    def __post_init__(self) -> None:
        # Defense-in-depth: cli/_bypass.validate_bypass_request is the canonical
        # gate (incl. trust-store checks); but BypassRequest may also be created by
        # tests / future internal callers. Mirror the ≥10-char rule here.
        if self.bypass_phase_gate:
            text = (self.justification or "").strip()
            if len(text) < _BYPASS_MIN_JUSTIFICATION_LEN:
                raise ValueError(
                    f"bypass_phase_gate=True requires a justification of at least "
                    f"{_BYPASS_MIN_JUSTIFICATION_LEN} non-whitespace characters; "
                    f"got {len(text)}"
                )


def _resolve_user() -> str:
    """Best-effort user identity for bypass journal entries.

    Tries git config user.email (5s timeout); falls back to USER/USERNAME env var.
    """
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    # Windows uses USERNAME; POSIX uses USER
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def _make_hook_rejected_entry(
    *,
    seq: int,
    ts: str,
    hook_name: str,
    target_path: str,
    reason: str,
    error_code: str,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor="hooks.runner",
        kind=_HOOK_REJECTED_KIND,
        target_id=target_path,
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={
            "hook": hook_name,
            "target": target_path,
            "reason": reason,
            "error_code": error_code,
        },
    )


def _make_bypass_entry(
    *,
    seq: int,
    ts: str,
    target_path: str,
    justification: str,
    justification_truncated: bool,
    user: str,
    phase_attempted: int | None,
    missing_signoff_path: str | None,
) -> JournalEntry:
    payload: dict[str, object] = {
        "target": target_path,
        "justification": justification,
        "justification_truncated": justification_truncated,
        "user": user,
        "phase_attempted": phase_attempted,
        "missing_signoff_path": missing_signoff_path,
    }
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor="hooks.runner",
        kind=_BYPASS_APPLIED_KIND,
        target_id=target_path,
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload=payload,
    )


async def _do_journal_append(entry: JournalEntry, journal_path: Path) -> None:  # pragma: no cover
    """Deferred journal append; isolated for testability via mock."""
    from sdlc.journal import append  # noqa: PLC0415 — deferred to avoid POSIX-only cost

    await append(entry, journal_path)


def _get_phase_for_path(target_path: str) -> int | None:
    """Return the phase number (1/2/3) for a target_path, or None if not a phase path."""
    from pathlib import PurePosixPath  # noqa: PLC0415

    parts = PurePosixPath(target_path).parts
    if not parts:  # pragma: no cover
        return None
    leading = parts[0]
    if leading.startswith("01-"):
        return 1
    if leading.startswith("02-"):
        return 2
    if leading.startswith("03-"):
        return 3
    return None


def _check_is_phase_gate_hook(hook: Callable[[HookPayload], HookDecision]) -> bool:
    """True if hook IS phase_gate or wraps it."""
    from sdlc.hooks.builtin.phase_gate import phase_gate  # noqa: PLC0415

    return hook is phase_gate or _is_phase_gate_closure(hook)  # type: ignore[comparison-overlap]


async def _append_deny_journal(
    decision: HookDecision, *, ts: str, payload: HookPayload, journal_path: Path | None
) -> None:
    """Append a hook_rejected journal entry; no-op when journal_path is None."""
    if journal_path is None:
        return
    from sdlc.journal import allocate_next_seq_for_append_sync  # noqa: PLC0415

    seq = await asyncio.to_thread(allocate_next_seq_for_append_sync, journal_path)
    await _do_journal_append(
        _make_hook_rejected_entry(
            seq=seq,
            ts=ts,
            hook_name=decision.hook_name or "unknown",
            target_path=payload.target_path,
            reason=decision.reason or "",
            error_code=decision.error_code or "",
        ),
        journal_path,
    )


async def _append_bypass_journal(
    *,
    seq: int,
    ts: str,
    payload: HookPayload,
    justification: str,
    bypassed_phase: int,
    journal_path: Path,
) -> None:
    raw = justification[:_BYPASS_MAX_JUSTIFICATION_LEN]
    signoff_path = f".claude/state/signoffs/phase-{bypassed_phase - 1}.yaml"
    await _do_journal_append(
        _make_bypass_entry(
            seq=seq,
            ts=ts,
            target_path=payload.target_path,
            justification=raw,
            justification_truncated=len(justification) > _BYPASS_MAX_JUSTIFICATION_LEN,
            user=_resolve_user(),
            phase_attempted=bypassed_phase,
            missing_signoff_path=signoff_path,
        ),
        journal_path,
    )


async def run_hook_chain(
    payload: HookPayload,
    *,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    journal_path: Path | None = None,
    bypass_phase_gate: bool = False,
    justification: str | None = None,
) -> HookDecision:
    """Run hooks in declaration order; first deny short-circuits (AC3, Decision D1).

    Args:
        payload: Pre-built HookPayload for the write.
        hooks: Ordered tuple of hook callables — first deny wins.
        journal_path: Absolute path to the journal.log; None only in unit tests.
        bypass_phase_gate: When True, phase_gate hook returns allow immediately
            (naming_validator is NEVER bypassed).
        justification: Required when bypass_phase_gate=True (min 10 chars).

    Returns:
        HookDecision.allow() if all hooks pass; HookDecision.deny(...) on first failure.
    """
    if bypass_phase_gate and (
        not justification or len(justification) < _BYPASS_MIN_JUSTIFICATION_LEN
    ):
        raise ValueError(
            f"bypass_phase_gate=True requires a justification of at least "
            f"{_BYPASS_MIN_JUSTIFICATION_LEN} characters"
        )

    ts = now_rfc3339_utc_ms()
    bypassed_phase: int | None = None

    for hook in hooks:
        if bypass_phase_gate and _check_is_phase_gate_hook(hook):
            phase = _get_phase_for_path(payload.target_path)
            if phase in (2, 3):
                bypassed_phase = phase
            continue

        try:
            decision = hook(payload)
        except HookError as exc:
            decision = HookDecision.deny(
                hook_name=getattr(hook, "__name__", "unknown"),
                reason=str(exc),
                error_code="hook_internal_error",
            )

        if decision.decision == "deny":
            await _append_deny_journal(decision, ts=ts, payload=payload, journal_path=journal_path)
            return decision

    if bypass_phase_gate and bypassed_phase is not None and justification and journal_path:
        from sdlc.journal import allocate_next_seq_for_append_sync  # noqa: PLC0415

        seq_bp = await asyncio.to_thread(allocate_next_seq_for_append_sync, journal_path)
        await _append_bypass_journal(
            seq=seq_bp,
            ts=ts,
            payload=payload,
            justification=justification,
            bypassed_phase=bypassed_phase,
            journal_path=journal_path,
        )

    return HookDecision.allow()


def _is_phase_gate_closure(hook: Callable[[HookPayload], HookDecision]) -> bool:
    """Check if a function wraps phase_gate (for dispatcher-created hook wrappers).

    Two detection strategies:
    1. Explicit marker: caller sets hook.__is_phase_gate__ = True (preferred for dispatchers).
    2. co_names heuristic: phase_gate is a global name used inside the function body.
    """
    if getattr(hook, "__is_phase_gate__", False):
        return True
    code = getattr(hook, "__code__", None)
    if code is None:
        return False
    # phase_gate accessed as a module-level global inside a wrapper function
    return "phase_gate" in code.co_names

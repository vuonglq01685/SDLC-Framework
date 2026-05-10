"""phase_gate builtin hook — phase boundary enforcement (FR37, AC5, Story 2A.4 + 2A.7).

AC11/D1 decision: D2 chosen — signoff_reader injected via DI (no direct import of
sdlc.signoff from hooks/). The dispatcher (Story 2A.6) passes signoff.compute_state
at chain-construction time. Boundary rule preserved: hooks/ does not import signoff/.

EPIC-2A-DEBT-PHASE-GATE-READ — RESOLVED in Story 2A.7 Task 6. The direct
yaml.safe_load reader has been replaced with the compute_state DI parameter.

Architecture §1109: hooks/ does NOT import engine/ or dispatcher/ or signoff/.
Boundary (AC9): this module imports only stdlib + sdlc.contracts + sdlc.hooks.runner.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Callable, Final

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.runner import HookDecision

_HOOK_NAME: Final[str] = "phase_gate"

# SignoffReaderType: (phase: int, repo_root: Path) -> str
# Returns a SignoffState value string. Compared to "approved" (SignoffState.APPROVED).
# The caller (dispatcher) injects sdlc.signoff.compute_state wrapped as a positional callable.
SignoffReaderType = Callable[[int, Path], str]


def _deny_gate(reason: str) -> HookDecision:
    return HookDecision.deny(
        hook_name=_HOOK_NAME,
        reason=reason,
        error_code="phase_gate_violation",
    )


def _get_leading_dir(target_path: str) -> str | None:
    """Extract leading directory from a POSIX path string (defense against Windows sep)."""
    parts = PurePosixPath(target_path).parts
    if not parts:
        return None
    return parts[0]


def _check_state(
    signoff_reader: SignoffReaderType,
    required_phase: int,
    repo_root: Path,
    gate_phase: int,
) -> HookDecision | None:
    """Call signoff_reader; return deny unless result == 'approved'.

    Any exception from the reader (SignoffError, malformed record) is treated as
    a deny to preserve the fail-safe posture of the old yaml.safe_load path.
    """
    try:
        state = signoff_reader(required_phase, repo_root)
    except Exception as exc:  # noqa: BLE001
        return _deny_gate(
            f"phase-gate violation: Phase {gate_phase} path requires Phase "
            f"{required_phase} signoff; reader raised: {exc}"
        )

    if state == "approved":
        return None  # allow

    _state_hints = {
        "awaiting-signoff": "not found",
        "drafted-not-approved": "drafted but not yet approved",
        "invalidated-by-replan": "invalidated by replan",
    }
    # Normalize str-enum to its value string; Python 3.11+ changed str(enum) to show
    # the class.member name rather than the value, breaking dict lookup.
    state_key = state.value if hasattr(state, "value") else str(state)
    hint = _state_hints.get(state_key, state_key)
    return _deny_gate(
        f"phase-gate violation: Phase {gate_phase} path requires Phase "
        f"{required_phase} signoff == approved; current state: {hint}"
    )


def phase_gate(
    payload: HookPayload,
    *,
    repo_root: Path,
    bypass_phase_gate: bool = False,
    signoff_reader: SignoffReaderType,
) -> HookDecision:
    """Gate writes to Phase 2/3 paths on the canonical signoff state (AC7, D2).

    Phase 1 paths (01-Requirement/) → always allow.
    Phase 2 paths (02-Architecture/) → require compute_state(phase=1) == APPROVED.
    Phase 3 paths (03-Implementation/) → require compute_state(phase=2) == APPROVED.
    All other paths (.claude/, tests/, _bmad-output/, etc.) → allow.

    signoff_reader is required (no default): the dispatcher must inject it explicitly.
    AWAITING_SIGNOFF, DRAFTED_NOT_APPROVED, and INVALIDATED_BY_REPLAN all deny.
    """
    if bypass_phase_gate:
        return HookDecision.allow()

    leading = _get_leading_dir(payload.target_path)

    if leading is None or leading.startswith("01-"):
        return HookDecision.allow()

    if leading.startswith("02-"):
        deny = _check_state(signoff_reader, required_phase=1, repo_root=repo_root, gate_phase=2)
        return deny if deny is not None else HookDecision.allow()

    if leading.startswith("03-"):
        deny = _check_state(signoff_reader, required_phase=2, repo_root=repo_root, gate_phase=3)
        return deny if deny is not None else HookDecision.allow()

    # Non-phase paths (.claude/, tests/, _bmad-output/, config files, etc.)
    return HookDecision.allow()

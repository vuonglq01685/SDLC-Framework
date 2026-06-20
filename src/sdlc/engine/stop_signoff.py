"""STOP trigger 2 — signoff required detection (Story 4.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sdlc.engine.stop_triggers import StopDecision
from sdlc.errors import SignoffError
from sdlc.signoff import PHASE_DIR_MAP, SignoffState, compute_state
from sdlc.state.model import State

# Phase boundary artifact whose presence on disk proves the phase was entered —
# avoids a spurious greenfield halt (AC2/D3). Keyed by phase number, in ladder order.
_BOUNDARY_ARTIFACT_REL: Final[dict[int, str]] = {
    1: "01-Requirement/01-PRODUCT.md",
    2: "02-Architecture/ARCHITECTURE.md",
}

_HALTING_STATES = frozenset({SignoffState.AWAITING_SIGNOFF, SignoffState.DRAFTED_NOT_APPROVED})


class SignoffRequiredTrigger:
    """Halt when a phase signoff is required and not yet approved."""

    trigger_id = "signoff_required"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        phase, phase_state = _first_unsigned_phase(repo_root)
        if phase is None or phase_state is None:
            return StopDecision(fired=False)

        phase_dir = PHASE_DIR_MAP.get(phase)
        if phase_dir is None:
            return StopDecision(fired=False)

        target = f"{phase_dir}/SIGNOFF.md"
        reason = (
            f"phase {phase} signoff required (state={phase_state.value}); "
            f"sign via /sdlc-signoff {phase}"
        )
        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=target,
            reason=reason,
        )


def _first_unsigned_phase(repo_root: Path) -> tuple[int | None, SignoffState | None]:
    """Return the first phase boundary that requires signoff (D3a ladder)."""
    for phase in _BOUNDARY_ARTIFACT_REL:
        try:
            phase_state = compute_state(phase=phase, repo_root=repo_root)
        except (SignoffError, OSError):
            return None, None
        if phase_state in _HALTING_STATES:
            if _boundary_crossed(repo_root, phase):
                return phase, phase_state
            return None, None
        if phase_state != SignoffState.APPROVED:
            return None, None
    return None, None


def _boundary_crossed(repo_root: Path, phase: int) -> bool:
    """True when phase work exists on disk — avoids spurious halt on greenfield (AC2/D3)."""
    rel = _BOUNDARY_ARTIFACT_REL.get(phase)
    return rel is not None and (repo_root / rel).is_file()

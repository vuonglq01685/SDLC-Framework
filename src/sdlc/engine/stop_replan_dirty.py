"""STOP trigger 4 — replan-dirty items detection (Story 4.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sdlc.engine.stop_triggers import StopDecision
from sdlc.signoff import SignoffState, compute_state
from sdlc.state.model import State

_DIRTY_PHASES: Final[tuple[int, ...]] = (1, 2)


class ReplanDirtyTrigger:
    """Halt when a signoff phase is invalidated by replan (INVALIDATED_BY_REPLAN)."""

    trigger_id = "replan_dirty"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        dirty_phases: list[int] = []
        for phase in _DIRTY_PHASES:
            if (
                compute_state(phase=phase, repo_root=repo_root)
                == SignoffState.INVALIDATED_BY_REPLAN
            ):
                dirty_phases.append(phase)

        if not dirty_phases:
            return StopDecision(fired=False)

        dirty_ids = [f"phase-{phase}" for phase in sorted(dirty_phases)]
        target = dirty_ids[0]
        reason = f"replan-dirty: {', '.join(dirty_ids)} awaiting re-signoff"

        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=target,
            reason=reason,
        )

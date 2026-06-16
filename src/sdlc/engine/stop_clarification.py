"""STOP trigger 1 — open clarification presence detection (Story 4.2)."""

from __future__ import annotations

from pathlib import Path

from sdlc.engine.stop_triggers import StopDecision
from sdlc.state.model import State

_CLARIFICATIONS_DIR_REL = ".claude/state/clarifications"
_OPEN_CLARIFICATION_NAME = "open_clarification.md"


class OpenClarificationTrigger:
    """Detect ``open_clarification.md`` under ``.claude/state/clarifications/<id>/``."""

    trigger_id = "open_clarification"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        clarifications_dir = repo_root / _CLARIFICATIONS_DIR_REL
        if not clarifications_dir.is_dir():
            return StopDecision(fired=False)

        candidates: list[Path] = []
        for clar_id_dir in sorted(clarifications_dir.iterdir()):
            if not clar_id_dir.is_dir():
                continue
            clar_file = clar_id_dir / _OPEN_CLARIFICATION_NAME
            if clar_file.is_file():
                candidates.append(clar_file)

        if not candidates:
            return StopDecision(fired=False)

        target = candidates[0]
        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=str(target),
        )

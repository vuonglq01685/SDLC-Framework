"""STOP trigger registry — ordered composition seam (Story 4.2, D1)."""

from __future__ import annotations

from pathlib import Path

from sdlc.engine.stop_agent_failed import AgentFailedTrigger
from sdlc.engine.stop_clarification import OpenClarificationTrigger
from sdlc.engine.stop_pr_ready import PrReadyStoryTrigger
from sdlc.engine.stop_replan_dirty import ReplanDirtyTrigger
from sdlc.engine.stop_signoff import SignoffRequiredTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger
from sdlc.state.model import State

# Priority order: first-listed trigger wins when multiple could fire (C7).
# Stories 4.3-4.9 append new triggers to this tuple after review.
_ORDERED_TRIGGERS: tuple[StopTrigger, ...] = (
    OpenClarificationTrigger(),
    SignoffRequiredTrigger(),
    PrReadyStoryTrigger(),
    ReplanDirtyTrigger(),
    AgentFailedTrigger(),
)

_extra_triggers: list[StopTrigger] = []


def ordered_triggers() -> tuple[StopTrigger, ...]:
    """Return the full trigger list: composed defaults plus runtime registrations."""
    return _ORDERED_TRIGGERS + tuple(_extra_triggers)


def register(trigger: StopTrigger) -> None:
    """Append a trigger for Layer-2 stories that register at runtime."""
    if not isinstance(trigger, StopTrigger):
        raise TypeError(
            "register expects a StopTrigger with `trigger_id: str` and "
            f"`check(*, repo_root, state) -> StopDecision` (got {type(trigger).__name__})"
        )
    _extra_triggers.append(trigger)


def check_all(*, repo_root: Path, state: State) -> StopDecision:
    """Consult triggers in priority order; return the first fired decision."""
    for trigger in ordered_triggers():
        decision = trigger.check(repo_root=repo_root, state=state)
        if decision.fired:
            return decision
    return StopDecision(fired=False)

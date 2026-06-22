"""STOP trigger registry — ordered composition seam (Story 4.2, D1)."""

from __future__ import annotations

from pathlib import Path

from sdlc.engine.stop_agent_failed import AgentFailedTrigger
from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger
from sdlc.engine.stop_clarification import OpenClarificationTrigger
from sdlc.engine.stop_high_risk import HighRiskPathTrigger
from sdlc.engine.stop_pr_ready import PrReadyStoryTrigger
from sdlc.engine.stop_replan_dirty import ReplanDirtyTrigger
from sdlc.engine.stop_signoff import SignoffRequiredTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger
from sdlc.state.model import State

# Cross-trigger precedence policy (CR4.8-W2 / Epic-4 retro D3). When 2+ triggers fire on
# the same disk state, the FIRST listed wins (check_all short-circuits). The order encodes
# urgency: irrecoverability -> loop-liveness -> human-blocked -> positive completion.
#   1. high_risk_path      CRITICAL, irreversible side effect — the declared anchor (#1).
#   2. agent_failed        the loop is stuck; surface it before any human-blocked or
#                          completion signal so the STOP banner (Story 5.19) shows the
#                          real blocker. (D3: moved up from #6.)
#   3. open_clarification  human-blocked: a decision is pending. The 3<->4 order is
#   4. signoff_required    load-bearing — mad-mode auto-resolves clarifications before
#                          signoffs (auto_mad), so it must not change.
#   5. replan_dirty        plan drift needs reconciliation.
#   6. bug_awaiting_decide a logged bug awaits a `decide` verb.
#   7. pr_ready_story      LOW, a positive completion signal; never mask a more urgent
#                          trigger, so it sorts last. (D3: moved down from #4.)
# watchdog_timeout is NOT in this tuple: it short-circuits in auto_loop.py BEFORE
# check_all(), so it architecturally pre-empts every registry trigger (pinned by test,
# not by a registry position). Stories 4.3-4.9 appended triggers here in arrival order;
# D3 reordered them to the urgency policy above.
_ORDERED_TRIGGERS: tuple[StopTrigger, ...] = (
    HighRiskPathTrigger(),
    AgentFailedTrigger(),
    OpenClarificationTrigger(),
    SignoffRequiredTrigger(),
    ReplanDirtyTrigger(),
    BugAwaitingDecideTrigger(),
    PrReadyStoryTrigger(),
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

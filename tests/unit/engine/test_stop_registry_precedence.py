"""Cross-trigger precedence tests for the STOP registry (CR4.8-W2 / Epic-4 retro D3).

`check_all` is a pure first-match over `ordered_triggers()`, so precedence is fully
determined by (1) the static order of `_ORDERED_TRIGGERS` and (2) the first-match
short-circuit. These tests pin both: the exact ratified order (the authoritative D3
regression), index assertions for the headline reorder (agent_failed up, pr_ready_story
down, the load-bearing open_clarification < signoff_required), and the first-match
semantics via stub triggers — together they fix the winner for ANY co-fire without a
fragile multi-trigger disk fixture.

Engine import is POSIX-only in v1, so this runs on the CI POSIX legs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.engine import stop_registry
from sdlc.engine.stop_triggers import StopDecision
from sdlc.state.model import State

pytestmark = pytest.mark.unit

# The ratified D3 order (highest priority first): irrecoverability -> loop-liveness ->
# human-blocked -> positive completion. See stop_registry._ORDERED_TRIGGERS policy note.
_RATIFIED_ORDER = (
    "high_risk_path",
    "agent_failed",
    "open_clarification",
    "signoff_required",
    "replan_dirty",
    "bug_awaiting_decide",
    "pr_ready_story",
)


def _order() -> list[str]:
    return [t.trigger_id for t in stop_registry._ORDERED_TRIGGERS]


class _StubTrigger:
    """Minimal StopTrigger for first-match semantics tests (ignores repo_root/state)."""

    def __init__(self, trigger_id: str, *, fires: bool) -> None:
        self.trigger_id = trigger_id
        self._fires = fires

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        return StopDecision(fired=self._fires, trigger=self.trigger_id)


def test_ordered_triggers_match_ratified_precedence() -> None:
    # Authoritative D3 pin: any accidental reorder or mis-placed append fails here.
    assert tuple(_order()) == _RATIFIED_ORDER


def test_high_risk_path_remains_the_anchor() -> None:
    assert _order()[0] == "high_risk_path"


def test_agent_failed_outranks_loop_blocked_and_completion_triggers() -> None:
    # D3: agent_failed moved up to #2 — a stuck loop must surface before any
    # human-blocked or positive-completion trigger so the STOP banner shows it.
    order = _order()
    assert order.index("agent_failed") == 1
    for lower in ("replan_dirty", "bug_awaiting_decide", "pr_ready_story"):
        assert order.index("agent_failed") < order.index(lower)


def test_pr_ready_story_is_lowest_priority() -> None:
    # D3: pr_ready_story moved down to last — a completion signal never masks a more
    # urgent trigger.
    assert _order()[-1] == "pr_ready_story"


def test_open_clarification_outranks_signoff_required() -> None:
    # Load-bearing 3<->4 order: mad-mode auto-resolves clarifications before signoffs,
    # so open_clarification must precede signoff_required.
    order = _order()
    assert order.index("open_clarification") < order.index("signoff_required")


def test_check_all_returns_first_fired_trigger_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = _StubTrigger("first", fires=True)
    second = _StubTrigger("second", fires=True)
    monkeypatch.setattr(stop_registry, "ordered_triggers", lambda: (first, second))
    decision = stop_registry.check_all(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "first"


def test_check_all_skips_non_firing_then_returns_next_fired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    quiet = _StubTrigger("quiet", fires=False)
    loud = _StubTrigger("loud", fires=True)
    monkeypatch.setattr(stop_registry, "ordered_triggers", lambda: (quiet, loud))
    decision = stop_registry.check_all(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "loud"

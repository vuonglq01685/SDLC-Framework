"""Unit tests for engine/stop_triggers.py (Story 4.1, AC5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop
from sdlc.state.model import State

pytestmark = pytest.mark.unit


def test_check_stop_returns_not_fired_by_default(tmp_path: Path) -> None:
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)
    assert decision.trigger is None
    assert decision.target is None


def test_stop_trigger_protocol_shape() -> None:
    class _StubTrigger:
        trigger_id = "stub"

        def check(self, *, repo_root: Path, state: State) -> StopDecision:
            _ = repo_root, state
            return StopDecision(fired=False)

    assert isinstance(_StubTrigger(), StopTrigger)

"""Unit tests for engine/watchdog.py (Story 4.9)."""

from __future__ import annotations

import pytest

from sdlc.engine.watchdog import make_watchdog_stop_decision, watchdog_deadline_exceeded

pytestmark = pytest.mark.unit


def test_watchdog_deadline_exceeded_false_before_timeout() -> None:
    assert watchdog_deadline_exceeded(0.0, now_monotonic=179.0, timeout_minutes=3.0) is False


def test_watchdog_deadline_exceeded_true_at_boundary() -> None:
    assert watchdog_deadline_exceeded(0.0, now_monotonic=180.0, timeout_minutes=3.0) is True


def test_make_watchdog_stop_decision_shape() -> None:
    stop = make_watchdog_stop_decision("/repo", elapsed_minutes=30.7)
    assert stop.fired is True
    assert stop.trigger == "watchdog_timeout"
    assert stop.target == "/repo"
    assert stop.reason == "elapsed ~30 min"


def test_make_watchdog_stop_decision_sub_minute_renders_seconds() -> None:
    # A sub-minute timeout (e.g. the 0.05-min integration value) must not truncate
    # to the misleading "~0 min" -- it renders seconds instead.
    stop = make_watchdog_stop_decision("/repo", elapsed_minutes=0.05)
    assert stop.reason == "elapsed ~3 s"

"""Auto-loop status fold tests for sdlc.state.projection — sticky-halt (ADR-038 / retro D4).

Split out of test_state_projection.py to keep both files under the 400-LOC cap
(Architecture §765 / NFR-MAINT-3). Drives _project_entries directly with Python lists to
stay cross-platform.
"""

from __future__ import annotations

import pytest

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.state.projection import _project_entries

_TS = "2026-05-08T00:00:00.000Z"
_AFTER = "sha256:" + "a" * 64


def _entry(
    *,
    kind: str,
    seq: int = 0,
    payload: dict[str, object] | None = None,
    target_id: str = "auto-loop",
    schema_version: int = 1,
) -> JournalEntry:
    """Build a valid JournalEntry for fold tests."""
    return JournalEntry.model_validate(
        {
            "schema_version": schema_version,
            "monotonic_seq": seq,
            "ts": _TS,
            "actor": "test",
            "kind": kind,
            "target_id": target_id,
            "before_hash": None,
            "after_hash": _AFTER,
            "payload": payload if payload is not None else {},
        }
    )


# ---------------------------------------------------------------------------
# Sticky-halt fold (ADR-038 / Epic-4 retro D4 / CR4.2-W3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_project_halted_is_sticky_against_clean_stopped_iteration() -> None:
    # A clean `stopped` iteration recorded AFTER a halt must NOT clear it — otherwise a
    # journal ending stop_trigger_raised -> stopped replays to idle and the halt is lost
    # permanently (Story 5.19 STOP banner load-bears this).
    entries = [
        _entry(kind="stop_trigger_raised", seq=0, payload={"trigger": "agent_failed"}),
        _entry(
            kind="auto_loop_iteration",
            seq=1,
            payload={"action": "stopped", "reason": "max_iterations reached"},
        ),
    ]
    state = _project_entries(entries)
    assert state.auto_loop_status == "halted"
    assert state.stop_reason == "agent_failed"


@pytest.mark.unit
def test_project_stop_triggered_then_stopped_stays_halted() -> None:
    # The other halt kind (stop_triggered) is equally sticky against a clean stop.
    entries = [
        _entry(kind="stop_triggered", seq=0, payload={"trigger": "high_risk_path"}),
        _entry(kind="auto_loop_iteration", seq=1, payload={"action": "stopped"}),
    ]
    state = _project_entries(entries)
    assert state.auto_loop_status == "halted"
    assert state.stop_reason == "high_risk_path"


@pytest.mark.unit
def test_project_genuine_dispatch_clears_a_prior_halt() -> None:
    # A real resume (dispatch/continued) DOES clear the halt — the blocker was resolved and
    # the loop restarted. Guards against over-sticking (latching halted forever).
    entries = [
        _entry(kind="stop_trigger_raised", seq=0, payload={"trigger": "agent_failed"}),
        _entry(kind="auto_loop_iteration", seq=1, payload={"action": "dispatch"}),
    ]
    state = _project_entries(entries)
    assert state.auto_loop_status == "running"
    assert state.stop_reason is None


@pytest.mark.unit
def test_project_clean_stopped_without_prior_halt_folds_to_idle() -> None:
    # The sticky-halt fix must NOT change the normal case: a `stopped` iteration with no
    # prior halt still settles to idle (bounded max_iterations exit).
    entries = [
        _entry(kind="auto_loop_iteration", seq=0, payload={"action": "dispatch"}),
        _entry(kind="auto_loop_iteration", seq=1, payload={"action": "stopped"}),
    ]
    state = _project_entries(entries)
    assert state.auto_loop_status == "idle"
    assert state.stop_reason is None

"""Unit tests for engine/stop_clarification.py (Story 4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.engine.stop_clarification import OpenClarificationTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop, register_stop_trigger
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_CLARIFICATIONS = ".claude/state/clarifications"


def _write_open_clarification(repo_root: Path, clar_id: str) -> Path:
    clar_dir = repo_root / _CLARIFICATIONS / clar_id
    clar_dir.mkdir(parents=True, exist_ok=True)
    path = clar_dir / "open_clarification.md"
    path.write_text("# open\n", encoding="utf-8")
    return path


def test_open_clarification_trigger_satisfies_protocol() -> None:
    assert isinstance(OpenClarificationTrigger(), StopTrigger)


def test_check_fires_when_open_clarification_exists(tmp_path: Path) -> None:
    path = _write_open_clarification(tmp_path, "clar-001")
    trigger = OpenClarificationTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(
        fired=True,
        trigger="open_clarification",
        target=str(path),
        reason=None,
    )


def test_check_not_fired_when_directory_missing(tmp_path: Path) -> None:
    trigger = OpenClarificationTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_directory_empty(tmp_path: Path) -> None:
    (tmp_path / _CLARIFICATIONS).mkdir(parents=True)
    trigger = OpenClarificationTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_multiple_clarifications_picks_lexically_first_id(tmp_path: Path) -> None:
    second = _write_open_clarification(tmp_path, "clar-z")
    first = _write_open_clarification(tmp_path, "clar-a")
    trigger = OpenClarificationTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == str(first)
    assert decision.target != str(second)


def test_register_stop_trigger_no_longer_raises() -> None:
    register_stop_trigger(OpenClarificationTrigger())


def test_registry_isolated_after_registration() -> None:
    # Canary for the autouse reset fixture (review P1): the prior test registered a
    # trigger; with isolation restored, the registry is back to just the static defaults.
    from sdlc.engine import stop_registry

    assert len(stop_registry.ordered_triggers()) == len(stop_registry._ORDERED_TRIGGERS)


def test_register_stop_trigger_rejects_non_conforming() -> None:
    # review P2: a malformed trigger must fail loud at registration, not later in check_all.
    class NotATrigger:
        pass

    with pytest.raises(TypeError):
        register_stop_trigger(NotATrigger())  # type: ignore[arg-type]


def test_check_stop_fires_via_registry(tmp_path: Path) -> None:
    _write_open_clarification(tmp_path, "clar-001")
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "open_clarification"


def test_projection_folds_stop_triggered_to_halted() -> None:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.state.projection import _project_entries

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts="2026-06-15T10:00:00.000Z",
        actor="auto_loop",
        kind="stop_triggered",
        target_id="open-clarification",
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={
            "trigger": "open_clarification",
            "target": ".claude/state/clarifications/clar-001/open_clarification.md",
            "correlation_id": "cid-1",
        },
    )
    state = _project_entries([entry])
    assert state.auto_loop_status == "halted"
    assert state.stop_reason == "open_clarification"

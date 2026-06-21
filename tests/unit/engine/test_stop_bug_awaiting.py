"""Unit tests for engine/stop_bug_awaiting.py (Story 4.8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_BUGS_DIR = ".claude/state/bugs"


def _write_awaiting_bug(
    repo_root: Path,
    bug_id: str,
    *,
    summary: str = "Login fails on Safari",
    state: str = "awaiting-decide",
) -> Path:
    bugs_dir = repo_root / _BUGS_DIR
    bugs_dir.mkdir(parents=True, exist_ok=True)
    path = bugs_dir / f"{bug_id}.yaml"
    payload: dict[str, str] = {"state": state}
    if summary:
        payload["summary"] = summary
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_bug_awaiting_decide_trigger_satisfies_protocol() -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    assert isinstance(BugAwaitingDecideTrigger(), StopTrigger)


def test_check_fires_when_awaiting_decide_bug_exists(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    _write_awaiting_bug(tmp_path, "bug-001", summary="Login fails on Safari")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(
        fired=True,
        trigger="bug_awaiting_decide",
        target="bug-001",
        reason="Login fails on Safari",
    )


def test_check_fires_without_summary_uses_fallback_reason(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    bugs_dir = tmp_path / _BUGS_DIR
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "bug-no-summary.yaml").write_text("state: awaiting-decide\n", encoding="utf-8")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == "bug-no-summary"
    assert decision.reason == "bug bug-no-summary"


def test_check_not_fired_when_directory_missing(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_directory_empty(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    (tmp_path / _BUGS_DIR).mkdir(parents=True)
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


@pytest.mark.parametrize("state", ["accepted", "rejected", "open"])
def test_check_not_fired_when_state_is_not_awaiting_decide(
    tmp_path: Path,
    state: str,
) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    _write_awaiting_bug(tmp_path, "bug-001", state=state)
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_on_malformed_yaml(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    bugs_dir = tmp_path / _BUGS_DIR
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "bug-bad.yaml").write_text("{{not valid yaml", encoding="utf-8")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_on_non_mapping_yaml(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    bugs_dir = tmp_path / _BUGS_DIR
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "bug-list.yaml").write_text("- item\n", encoding="utf-8")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_on_invalid_utf8_bytes(tmp_path: Path) -> None:
    """CR4.8-P1: a non-UTF-8 bug file raises UnicodeDecodeError (a ValueError,
    NOT an OSError) in read_text; the trigger must fail soft, not propagate and
    crash the unguarded post-dispatch check_stop sweep."""
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    bugs_dir = tmp_path / _BUGS_DIR
    bugs_dir.mkdir(parents=True)
    # 0x93 is a bare UTF-8 continuation byte (cp1252 smart-quote) → invalid UTF-8.
    (bugs_dir / "bug-bin.yaml").write_bytes(b"state: awaiting-decide\nsummary: \x93bad\n")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_check_fires_with_blank_summary_uses_fallback_reason(
    tmp_path: Path,
    blank: str,
) -> None:
    """CR4.8-P2: an empty/whitespace-only summary still halts but falls back to a
    usable reason instead of emitting an empty operator reason."""
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    bugs_dir = tmp_path / _BUGS_DIR
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "bug-blank.yaml").write_text(
        yaml.safe_dump({"state": "awaiting-decide", "summary": blank}, sort_keys=False),
        encoding="utf-8",
    )
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == "bug-blank"
    assert decision.reason == "bug bug-blank"


def test_multiple_awaiting_bugs_picks_lexically_first_id(tmp_path: Path) -> None:
    from sdlc.engine.stop_bug_awaiting import BugAwaitingDecideTrigger

    _write_awaiting_bug(tmp_path, "bug-z", summary="Later bug")
    _write_awaiting_bug(tmp_path, "bug-a", summary="First bug")
    trigger = BugAwaitingDecideTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == "bug-a"
    assert decision.reason == "First bug"


def test_check_stop_fires_via_registry(tmp_path: Path) -> None:
    _write_awaiting_bug(tmp_path, "bug-001")
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "bug_awaiting_decide"

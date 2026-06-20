"""Unit tests for engine/stop_agent_failed.py (Story 4.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.engine.stop_agent_failed import AgentFailedTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_JOURNAL_REL = ".claude/state/journal.log"
_STEP = "requirements"
_SPECIALIST = "product-strategist"
_TARGET_ID = f"{_STEP}/{_SPECIALIST}"
_EVENT_HASH = "sha256:" + "0" * 64


def _journal_path(repo_root: Path) -> Path:
    path = repo_root / _JOURNAL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_entry(journal_path: Path, seq: int, entry: JournalEntry) -> None:
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def _dispatch_attempt(seq: int, *, outcome: str, attempt: int) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=f"2026-06-18T10:00:{seq:02d}.000Z",
        actor="dispatcher",
        kind="dispatch_attempt",
        target_id=_TARGET_ID,
        before_hash=None if seq == 0 else _EVENT_HASH,
        after_hash=_EVENT_HASH,
        payload={"outcome": outcome, "attempt": attempt},
    )


def _stop_trigger_raised(seq: int, *, last_error: str = "runtime unavailable") -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=f"2026-06-18T10:00:{seq:02d}.000Z",
        actor="dispatcher",
        kind="stop_trigger_raised",
        target_id=_TARGET_ID,
        before_hash=_EVENT_HASH,
        after_hash=_EVENT_HASH,
        payload={
            "trigger": "agent_failure_after_retries",
            "specialist": _SPECIALIST,
            "step": _STEP,
            "epic_4_placeholder": True,
            "last_error": last_error,
        },
    )


def _write_terminal_failure_journal(repo_root: Path) -> None:
    journal = _journal_path(repo_root)
    _append_entry(journal, 1, _dispatch_attempt(1, outcome="retry", attempt=1))
    _append_entry(journal, 2, _dispatch_attempt(2, outcome="retry", attempt=2))
    _append_entry(journal, 3, _dispatch_attempt(3, outcome="failed", attempt=3))
    _append_entry(journal, 4, _stop_trigger_raised(4))


def test_agent_failed_trigger_satisfies_protocol() -> None:
    assert isinstance(AgentFailedTrigger(), StopTrigger)


def test_check_fires_on_terminal_stop_trigger_raised(tmp_path: Path) -> None:
    _write_terminal_failure_journal(tmp_path)
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "agent_failed"
    assert decision.target == _TARGET_ID
    assert decision.reason is not None
    assert f"agent={_SPECIALIST}" in decision.reason
    assert "attempts=3" in decision.reason
    assert "last_error=runtime unavailable" in decision.reason
    assert "debug=03-Implementation/agent_runs.jsonl" in decision.reason


def test_check_not_fired_when_journal_missing(tmp_path: Path) -> None:
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_without_stop_trigger_raised(tmp_path: Path) -> None:
    journal = _journal_path(tmp_path)
    _append_entry(journal, 1, _dispatch_attempt(1, outcome="retry", attempt=1))
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_after_fail_then_success(tmp_path: Path) -> None:
    journal = _journal_path(tmp_path)
    _append_entry(journal, 1, _dispatch_attempt(1, outcome="retry", attempt=1))
    _append_entry(journal, 2, _dispatch_attempt(2, outcome="retry", attempt=2))
    _append_entry(journal, 3, _dispatch_attempt(3, outcome="success", attempt=3))
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_success_supersedes_stale_failure(tmp_path: Path) -> None:
    journal = _journal_path(tmp_path)
    _append_entry(journal, 1, _dispatch_attempt(1, outcome="retry", attempt=1))
    _append_entry(journal, 2, _dispatch_attempt(2, outcome="retry", attempt=2))
    _append_entry(journal, 3, _dispatch_attempt(3, outcome="failed", attempt=3))
    _append_entry(journal, 4, _stop_trigger_raised(4))
    _append_entry(journal, 5, _dispatch_attempt(5, outcome="success", attempt=1))
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_stop_fires_via_registry(tmp_path: Path) -> None:
    _write_terminal_failure_journal(tmp_path)
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "agent_failed"


def test_projection_folds_stop_triggered_agent_failed_to_halted() -> None:
    from sdlc.state.projection import _project_entries

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts="2026-06-18T10:00:00.000Z",
        actor="auto_loop",
        kind="stop_triggered",
        target_id="agent_failed",
        before_hash=None,
        after_hash=_EVENT_HASH,
        payload={
            "trigger": "agent_failed",
            "target": _TARGET_ID,
            "correlation_id": "cid-1",
        },
    )
    state = _project_entries([entry])
    assert state.auto_loop_status == "halted"
    assert state.stop_reason == "agent_failed"


def test_check_fails_open_on_corrupt_journal_seq_regression(tmp_path: Path) -> None:
    # D-R2/P3: a seq-regressed (corrupt) journal makes iter_entries raise JournalError;
    # check() must fail open (fired=False) rather than crash the auto-loop STOP check.
    journal = _journal_path(tmp_path)
    _append_entry(journal, 5, _dispatch_attempt(5, outcome="failed", attempt=3))
    _append_entry(journal, 3, _stop_trigger_raised(3))  # seq 3 <= 5 -> JournalError on read
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "CR4.6-W2 (D-R1): a parallel-panel stop_trigger_raised uses target_id "
        "'{step}/parallel_agents' while the member dispatch_attempt rows use the real "
        "specialist target_id, so a successful resume never supersedes the raised entry. "
        "Real fix deferred (D-R1 option-b); this xfail documents the non-clearable-resume gap."
    ),
)
def test_parallel_panel_success_should_supersede_raised(tmp_path: Path) -> None:
    journal = _journal_path(tmp_path)
    real_target = f"{_STEP}/parallel-worker"
    parallel_target = f"{_STEP}/parallel_agents"
    _append_entry(
        journal,
        1,
        JournalEntry(
            schema_version=1,
            monotonic_seq=1,
            ts="2026-06-18T10:00:01.000Z",
            actor="dispatcher",
            kind="dispatch_attempt",
            target_id=real_target,
            before_hash=_EVENT_HASH,
            after_hash=_EVENT_HASH,
            payload={"outcome": "failed", "attempt": 1},
        ),
    )
    _append_entry(
        journal,
        2,
        JournalEntry(
            schema_version=1,
            monotonic_seq=2,
            ts="2026-06-18T10:00:02.000Z",
            actor="dispatcher",
            kind="stop_trigger_raised",
            target_id=parallel_target,
            before_hash=_EVENT_HASH,
            after_hash=_EVENT_HASH,
            payload={
                "trigger": "agent_failure_after_retries",
                "specialist": "parallel_agents",
                "step": _STEP,
                "epic_4_placeholder": True,
                "last_error": "panel failed",
            },
        ),
    )
    _append_entry(
        journal,
        3,
        JournalEntry(
            schema_version=1,
            monotonic_seq=3,
            ts="2026-06-18T10:00:03.000Z",
            actor="dispatcher",
            kind="dispatch_attempt",
            target_id=real_target,
            before_hash=_EVENT_HASH,
            after_hash=_EVENT_HASH,
            payload={"outcome": "success", "attempt": 1},
        ),
    )
    # DESIRED post-fix behavior: the successful resume clears the parallel failure.
    decision = AgentFailedTrigger().check(repo_root=tmp_path, state=State())
    assert decision.fired is False

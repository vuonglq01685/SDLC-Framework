"""Unit tests for engine/auto_loop.py (Story 4.1).

Mad-mode seam tests live in the sibling ``test_auto_loop_mad_mode.py``; shared
project-seed fixtures live in ``tests/_auto_loop_helpers.py`` (400-LOC cap split).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from _auto_loop_helpers import (
    _TASK_ID,
    _bootstrap_journal,
    _mock_runtime,
    _write_phase3_ready_project,
)
from sdlc.engine.auto_loop import run_auto_loop
from sdlc.engine.next_selector import resolve_next_action
from sdlc.journal import iter_entries
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_one_iteration_logs_auto_loop_iteration(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=dispatch,
        max_iterations=1,
    )
    assert result.iterations == 1
    assert result.last_action == "dispatch"
    dispatch.assert_awaited_once()
    entry = next(iter_entries(journal))
    assert entry.kind == "auto_loop_iteration"
    assert entry.payload["action"] == "dispatch"
    assert entry.payload["task_id"] == _TASK_ID


@pytest.mark.asyncio
async def test_no_ready_item_logs_stopped(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, stage="done")
    journal, runs = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock()
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=dispatch,
        max_iterations=1,
    )
    assert result.last_action == "stopped"
    dispatch.assert_not_awaited()
    assert next(iter_entries(journal)).payload["action"] == "stopped"


@pytest.mark.asyncio
async def test_second_iteration_rereads_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    calls = []

    async def _dispatch(**kwargs):
        calls.append(kwargs.get("task_id"))

    resolve_calls = 0
    original = resolve_next_action

    def _counting_resolve(repo_root):
        nonlocal resolve_calls
        resolve_calls += 1
        return original(repo_root)

    monkeypatch.setattr("sdlc.engine.auto_loop.resolve_next_action", _counting_resolve)
    await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_dispatch,
        max_iterations=2,
    )
    assert resolve_calls == 2
    assert len(calls) == 2


def test_projection_folds_auto_loop_iteration() -> None:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.state.projection import _project_entries

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts="2026-06-10T10:00:00.000Z",
        actor="auto_loop",
        kind="auto_loop_iteration",
        target_id="auto-loop-iter-1",
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={"iteration_seq": 1, "action": "dispatch", "correlation_id": "cid-1"},
    )
    assert _project_entries([entry]).auto_loop_status == "running"
    stopped = JournalEntry(
        schema_version=1,
        monotonic_seq=1,
        ts="2026-06-10T10:00:01.000Z",
        actor="auto_loop",
        kind="auto_loop_iteration",
        target_id="auto-loop-iter-2",
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={
            "iteration_seq": 2,
            "action": "stopped",
            "correlation_id": "cid-2",
            "reason": "all tasks complete",
        },
    )
    state2 = _project_entries([entry, stopped])
    assert state2.auto_loop_status == "idle"
    assert state2.stop_reason == "all tasks complete"


def test_projection_folds_stop_trigger_raised() -> None:
    # The real dispatcher emitter (dispatcher/_panel_helpers.py) writes payload key "trigger"
    # (not "trigger_kind") — the fold MUST recognize that key or a real halt stays invisible
    # on disk (code-review P4). This entry mirrors the production payload shape.
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.state.projection import _project_entries

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts="2026-06-10T10:00:00.000Z",
        actor="dispatcher",
        kind="stop_trigger_raised",
        target_id="task",
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={
            "trigger": "agent_failure_after_retries",
            "specialist": "code-author",
            "epic_4_placeholder": True,
        },
    )
    state = _project_entries([entry])
    assert state.auto_loop_status == "halted"
    assert state.stop_reason == "agent_failure_after_retries"
    # Forward-compat: the legacy "trigger_kind" key is still tolerated.
    legacy = JournalEntry(
        schema_version=1,
        monotonic_seq=1,
        ts="2026-06-10T10:00:01.000Z",
        actor="dispatcher",
        kind="stop_trigger_raised",
        target_id="task",
        before_hash=None,
        after_hash="sha256:" + "0" * 64,
        payload={"trigger_kind": "agent_failure", "reason": "retries exhausted"},
    )
    assert _project_entries([legacy]).auto_loop_status == "halted"


@pytest.mark.asyncio
async def test_replay_status_from_journal_file(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, stage="done")
    journal, runs = _bootstrap_journal(tmp_path)
    await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=AsyncMock(),
        max_iterations=1,
    )
    assert project_from_journal(journal).auto_loop_status == "idle"


@pytest.mark.asyncio
async def test_watchdog_halt_when_deadline_exceeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)

    times = iter([0.0, 200.0])

    def _fake_monotonic() -> float:
        return next(times, 200.0)

    monkeypatch.setattr("sdlc.engine.auto_loop.time.monotonic", _fake_monotonic)

    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=dispatch,
        max_iterations=1,
        watchdog_timeout_minutes=1.0,
    )
    assert result.halted is True
    assert result.stop_reason == "watchdog_timeout"
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "watchdog_timeout"


@pytest.mark.asyncio
async def test_watchdog_disabled_when_timeout_none(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=dispatch,
        max_iterations=1,
        watchdog_timeout_minutes=None,
    )
    assert result.halted is False
    assert "stop_triggered" not in [e.kind for e in iter_entries(journal)]


@pytest.mark.asyncio
async def test_ambiguity_triggers_brainstorm_then_halts_open_clarification(
    tmp_path: Path,
) -> None:
    import json

    from sdlc.engine.auto_brainstorm import AmbiguityContext, clarification_id_for

    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    summary = "ambiguous integration approach"
    ctx = AmbiguityContext(task_id=_TASK_ID, summary=summary)
    clar_id = clarification_id_for(ctx)

    async def _dispatch(**kwargs) -> None:
        signals = kwargs["repo_root"] / ".claude" / "state" / "ambiguity_signals"
        signals.mkdir(parents=True, exist_ok=True)
        (signals / f"{kwargs['task_id']}.json").write_text(
            json.dumps({"summary": summary}),
            encoding="utf-8",
        )

    async def _fake_brainstorm(repo_root: Path, **kwargs) -> str:
        clar_dir = repo_root / ".claude" / "state" / "clarifications" / clar_id
        clar_dir.mkdir(parents=True, exist_ok=True)
        (clar_dir / "open_clarification.md").write_text("# open\n", encoding="utf-8")
        return clar_id

    brainstorm = AsyncMock(side_effect=_fake_brainstorm)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sdlc.engine.auto_loop.run_auto_brainstorm", brainstorm)
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=_dispatch,
            max_iterations=1,
            auto_brainstorm=True,
        )

    brainstorm.assert_awaited_once()
    assert result.halted is True
    assert result.stop_reason == "open_clarification"


@pytest.mark.asyncio
async def test_no_ambiguity_signal_skips_brainstorm(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)

    with pytest.MonkeyPatch.context() as mp:
        brainstorm = AsyncMock()
        mp.setattr("sdlc.engine.auto_loop.run_auto_brainstorm", brainstorm)
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            max_iterations=1,
            auto_brainstorm=True,
        )

    brainstorm.assert_not_awaited()
    assert result.halted is False

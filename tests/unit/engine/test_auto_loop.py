"""Unit tests for engine/auto_loop.py (Story 4.1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sdlc.engine.auto_loop import run_auto_loop
from sdlc.engine.next_selector import resolve_next_action
from sdlc.journal import iter_entries
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.unit


def _mock_runtime(tmp_path: Path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _write_approved_signoffs(tmp_path: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    for phase, rel in (
        (1, "01-Requirement/01-PRODUCT.md"),
        (2, "02-Architecture/ARCHITECTURE.md"),
    ):
        artifact_path = tmp_path / rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
        artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
        write_record(
            SignoffRecord(
                phase=phase,
                artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
                approved_by="test",
                approved_at="2026-06-10T10:00:00.000Z",
                drafted_at="2026-06-10T09:00:00.000Z",
                validated_at="2026-06-10T10:00:00.000Z",
            ),
            repo_root=tmp_path,
        )


def _write_phase3_ready_project(tmp_path: Path, *, stage: str = "pending") -> None:
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    epics = tmp_path / "01-Requirement" / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / f"{_EPIC_ID}.json").write_text(json.dumps({"id": _EPIC_ID}), encoding="utf-8")
    stories = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    stories.mkdir(parents=True, exist_ok=True)
    (stories / f"{_STORY_ID}.json").write_text(json.dumps({"id": _STORY_ID}), encoding="utf-8")
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    tasks = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-first-task.json").write_text(
        json.dumps(
            {
                "id": _TASK_ID,
                "story_id": _STORY_ID,
                "label": "t",
                "stage": stage,
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )
    _write_approved_signoffs(tmp_path)


def _bootstrap_journal(tmp_path: Path) -> tuple[Path, Path]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal = (state_dir / "journal.log").resolve()
    journal.touch()
    state = (state_dir / "state.json").resolve()
    state.write_text("{}", encoding="utf-8")
    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").resolve()
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    return journal, runs


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

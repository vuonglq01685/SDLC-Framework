"""Integration tests — pr-ready story STOP trigger 4-cell matrix (Story 4.4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.engine.auto_loop import run_auto_loop
from sdlc.engine.next_selector import NextDecision
from sdlc.engine.stop_triggers import check_stop
from sdlc.journal import iter_entries
from sdlc.runtime.mock import MockAIRuntime
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _write_approved_signoffs(tmp_path: Path) -> None:
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


def _bootstrap_journal(tmp_path: Path) -> tuple[Path, Path, Path]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal = (state_dir / "journal.log").resolve()
    journal.touch()
    state = (state_dir / "state.json").resolve()
    state.write_text("{}", encoding="utf-8")
    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").resolve()
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    return journal, runs, state


def _force_dispatch_decision() -> NextDecision:
    return NextDecision(
        kind="dispatch_task",
        task_id=_TASK_ID,
        phase=3,
        reason="integration test: force dispatch so STOP-check runs after stub dispatch (C5)",
    )


@pytest.mark.asyncio
async def test_cell1_positive_pr_ready_halts_loop(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, stage="done")
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=dispatch,
            state_path=state_path,
            max_iterations=1,
        )
    assert result.halted is True
    assert result.stop_reason == "pr_ready_story"
    dispatch.assert_awaited_once()
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "pr_ready_story"
    assert stop_entries[0].payload["target"] == _STORY_ID
    assert stop_entries[0].payload["reason"] == f"/sdlc-publish-pr {_STORY_ID}"


@pytest.mark.asyncio
async def test_cell2_negative_task_not_done_continues_without_pr_ready_halt(
    tmp_path: Path,
) -> None:
    _write_phase3_ready_project(tmp_path, stage="pending")
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    dispatch = AsyncMock(return_value=None)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=dispatch,
        state_path=state_path,
        max_iterations=1,
    )
    assert result.halted is False
    assert result.stop_reason != "pr_ready_story"
    pr_ready_entries = [
        e
        for e in iter_entries(journal)
        if e.kind == "stop_triggered" and e.payload.get("trigger") == "pr_ready_story"
    ]
    assert pr_ready_entries == []
    dispatch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell3_termination_state_projection_reflects_halt(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, stage="done")
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(return_value=None),
            state_path=state_path,
            max_iterations=1,
        )
    projected = project_from_journal(journal)
    assert projected.auto_loop_status == "halted"
    assert projected.stop_reason == "pr_ready_story"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell4_resume_after_story_advanced_check_and_loop_continue(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, stage="done")
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=_force_dispatch_decision(),
    ):
        halted = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(return_value=None),
            state_path=state_path,
            max_iterations=1,
        )
    assert halted.halted is True
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    for child in tasks_dir.iterdir():
        child.unlink()
    tasks_dir.rmdir()
    assert check_stop(repo_root=tmp_path, state=State()).fired is False
    resumed = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=AsyncMock(return_value=None),
        state_path=state_path,
        max_iterations=1,
    )
    assert resumed.halted is False
    assert resumed.stop_reason != "pr_ready_story"

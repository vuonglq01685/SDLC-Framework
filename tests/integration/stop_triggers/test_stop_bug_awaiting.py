"""Integration tests — bug awaiting decide STOP trigger 4-cell matrix (Story 4.8)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from sdlc.engine.auto_loop import run_auto_loop
from sdlc.engine.stop_triggers import check_stop
from sdlc.journal import iter_entries
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration

_BUGS_DIR = ".claude/state/bugs"
_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


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


def _write_awaiting_bug(
    repo_root: Path,
    bug_id: str = "bug-001",
    *,
    summary: str = "Login fails on Safari",
) -> Path:
    bugs_dir = repo_root / _BUGS_DIR
    bugs_dir.mkdir(parents=True, exist_ok=True)
    path = bugs_dir / f"{bug_id}.yaml"
    path.write_text(
        yaml.safe_dump({"state": "awaiting-decide", "summary": summary}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _journal_kinds(journal: Path) -> list[str]:
    return [e.kind for e in iter_entries(journal)]


@pytest.mark.asyncio
async def test_cell1_positive_awaiting_bug_halts_loop(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    _write_awaiting_bug(tmp_path)
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
    assert result.halted is True
    assert result.stop_reason == "bug_awaiting_decide"
    dispatch.assert_awaited_once()
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "bug_awaiting_decide"
    assert stop_entries[0].payload["target"] == "bug-001"
    assert stop_entries[0].payload["reason"] == "Login fails on Safari"


@pytest.mark.asyncio
async def test_cell2_negative_no_awaiting_bug_continues_without_stop_triggered(
    tmp_path: Path,
) -> None:
    _write_phase3_ready_project(tmp_path)
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
    assert result.stop_reason != "bug_awaiting_decide"
    assert "stop_triggered" not in _journal_kinds(journal)
    dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_cell3_termination_state_projection_reflects_halt(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    _write_awaiting_bug(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
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
    assert projected.stop_reason == "bug_awaiting_decide"


@pytest.mark.asyncio
async def test_cell4_resume_after_triage_check_and_loop_continue(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    bug_path = _write_awaiting_bug(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
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
    bug_path.write_text(
        yaml.safe_dump({"state": "accepted", "summary": "Login fails on Safari"}, sort_keys=False),
        encoding="utf-8",
    )
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
    assert resumed.stop_reason != "bug_awaiting_decide"

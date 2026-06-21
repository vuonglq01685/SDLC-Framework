"""Integration tests — configurable watchdog timeout (Story 4.9, AC4)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from sdlc.engine.auto_loop import run_auto_loop
from sdlc.journal import iter_entries
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration

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


def _write_phase3_ready_project(tmp_path: Path) -> None:
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
                "stage": "pending",
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
    (tmp_path / "project.yaml").write_text("watchdog_timeout_minutes: 0.05\n", encoding="utf-8")
    return journal, runs, state


@pytest.mark.asyncio
async def test_watchdog_halts_within_grace_window(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)

    async def _slow_dispatch(**_kwargs: object) -> None:
        await asyncio.sleep(3.1)

    started = time.monotonic()
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_slow_dispatch,
        state_path=state_path,
        watchdog_timeout_minutes=0.05,
    )
    elapsed = time.monotonic() - started

    assert result.halted is True
    assert result.stop_reason == "watchdog_timeout"
    assert 3.0 <= elapsed <= 5.5

    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "watchdog_timeout"

    projected = project_from_journal(journal)
    assert projected.auto_loop_status == "halted"
    assert projected.stop_reason == "watchdog_timeout"


@pytest.mark.asyncio
async def test_watchdog_resume_resets_timer(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)

    call_count = 0

    async def _slow_once_then_fast(**_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(3.1)

    first = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_slow_once_then_fast,
        state_path=state_path,
        watchdog_timeout_minutes=0.05,
    )
    assert first.halted is True
    assert first.stop_reason == "watchdog_timeout"

    # Run 2 dispatches for ~2 s -- comfortably UNDER the 0.05-min (3 s) deadline. This
    # only stays below the deadline if the start anchor reset for this run: a regression
    # that hoisted `start_monotonic` to module scope would carry run 1's >3 s elapsed
    # forward and watchdog-halt this iteration. (AsyncMock + max_iterations=1 could not
    # tell "reset" from "too fast to time out" -- it never reached the deadline at all.)
    async def _under_deadline_dispatch(**_kwargs: object) -> None:
        await asyncio.sleep(2.0)

    second = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_under_deadline_dispatch,
        state_path=state_path,
        watchdog_timeout_minutes=0.05,
        max_iterations=1,
    )
    assert second.halted is False
    assert second.stop_reason != "watchdog_timeout"

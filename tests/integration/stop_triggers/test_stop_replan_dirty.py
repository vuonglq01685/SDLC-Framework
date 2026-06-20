"""Integration tests — replan-dirty STOP trigger 4-cell matrix (Story 4.5)."""

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
from sdlc.signoff import ArtifactRef, SignoffRecord, invalidate_record, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration

_NOW_UTC = "2026-06-18T10:00:00.000Z"
_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


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


def _journal_kinds(journal: Path) -> list[str]:
    return [e.kind for e in iter_entries(journal)]


def _force_dispatch_decision() -> NextDecision:
    return NextDecision(
        kind="dispatch_task",
        task_id=_TASK_ID,
        phase=3,
        reason="integration test: force dispatch past invalidated phase 1 (C5)",
    )


def _re_sign_phase(tmp_path: Path, phase: int, rel: str) -> None:
    artifact_path = tmp_path / rel
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=phase,
            artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
            approved_by="test",
            approved_at=_NOW_UTC,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_NOW_UTC,
        ),
        repo_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_cell1_positive_replan_dirty_halts_loop(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)
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
    assert result.stop_reason == "replan_dirty"
    dispatch.assert_awaited_once()
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "replan_dirty"
    assert str(stop_entries[0].payload["target"]).startswith("phase-")


@pytest.mark.asyncio
async def test_cell2_negative_no_dirty_phase_continues_without_stop_triggered(
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
    assert result.stop_reason != "replan_dirty"
    assert "stop_triggered" not in _journal_kinds(journal)
    dispatch.assert_awaited_once()
    # Positive control (review 2026-06-20): a negative result is only meaningful if the trigger is
    # wired into _ORDERED_TRIGGERS. Dirtying a phase in the SAME fixture must make check_stop fire
    # replan_dirty, so a regression dropping the trigger fails here instead of passing silently.
    invalidate_record(1, repo_root=tmp_path, reason="control", now_utc=_NOW_UTC)
    control = check_stop(repo_root=tmp_path, state=State())
    assert control.fired is True
    assert control.trigger == "replan_dirty"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell3_termination_state_projection_reflects_halt(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)
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
    assert projected.stop_reason == "replan_dirty"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell4_resume_after_re_sign_check_and_loop_continue(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)
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
    stop_count_after_halt = sum(1 for e in iter_entries(journal) if e.kind == "stop_triggered")
    _re_sign_phase(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
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
    assert resumed.stop_reason != "replan_dirty"
    # The resumed run emitted NO new stop_triggered entry — proves the loop genuinely continued
    # rather than the bounded max_iterations=1 exit merely masking a re-halt (review 2026-06-20).
    stop_count_after_resume = sum(1 for e in iter_entries(journal) if e.kind == "stop_triggered")
    assert stop_count_after_resume == stop_count_after_halt


@pytest.mark.asyncio
async def test_cell1b_mid_dispatch_invalidation_halts_via_real_selector(tmp_path: Path) -> None:
    """High-fidelity production path (review 2026-06-20, D-R1 option-b): no resolve_next_action
    patch.

    Phases 1 & 2 are APPROVED at scan, so the REAL ``next_selector`` returns ``dispatch_task`` and
    the loop dispatches. The dispatched specialist then invalidates phase 1 mid-iteration
    (simulating ``sdlc replan`` during implementation), and the UN-patched post-dispatch
    ``check_stop`` fires ``replan_dirty`` because ``check()`` re-reads disk rather than the stale
    pre-dispatch snapshot — the loop-reachable path the forced-dispatch cells (1/3/4) cannot prove.
    """
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)

    async def _invalidating_dispatch(**_kwargs: object) -> None:
        invalidate_record(1, repo_root=tmp_path, reason="replan-during-impl", now_utc=_NOW_UTC)

    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_invalidating_dispatch,
        state_path=state_path,
        max_iterations=1,
    )
    assert result.halted is True
    assert result.stop_reason == "replan_dirty"
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "replan_dirty"
    assert stop_entries[0].payload["target"] == "phase-1"

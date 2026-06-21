"""Integration tests — agent-failed STOP trigger 4-cell matrix (Story 4.6)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.core import dispatch
from sdlc.engine.auto_loop import run_auto_loop
from sdlc.engine.stop_triggers import check_stop
from sdlc.errors import DispatchError
from sdlc.journal import iter_entries
from sdlc.runtime.abc import AgentResult
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

pytestmark = pytest.mark.integration

_SPECIALIST_NAME = "product-strategist"
_TARGET_REL = "docs/product.md"
_STEP = WorkflowSpec(
    schema_version=1,
    name="requirements",
    slash_command="sdlc-start",
    primary_agent=_SPECIALIST_NAME,
    parallel_agents=(),
    synthesizer_agent=None,
    write_globs={_SPECIALIST_NAME: (_TARGET_REL,)},
)
_FM = SpecialistFrontmatter(
    schema_version=1,
    name=_SPECIALIST_NAME,
    title="Product Strategist",
    icon="📋",
    model="claude-opus-4-5",
    description="Writes product requirements.",
    write_globs=(_TARGET_REL,),
)
_SPECIALIST = Specialist(
    frontmatter=_FM,
    body="You are a product strategist.",
    source_path=Path("specialists/product-strategist.md"),
)
_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


def _make_registry() -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({_SPECIALIST.frontmatter.name: _SPECIALIST}))


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


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


def _journal_kinds(journal: Path) -> list[str]:
    return [e.kind for e in iter_entries(journal)]


def _make_retry_dispatch_fn(side_effect: object):
    async def _dispatch_fn(
        *,
        task_id: str,
        repo_root: Path,
        journal_path: Path,
        agent_runs_path: Path,
        runtime: object,
        registry: SpecialistRegistry,
        correlation_id: str,
    ) -> None:
        _ = task_id, runtime, registry, correlation_id
        failing_runtime = AsyncMock()
        if isinstance(side_effect, AgentResult):
            # A bare success result must be RETURNED, not assigned to side_effect:
            # AgentResult is a pydantic BaseModel (iterable), so Mock would iterate
            # it into (field, value) tuples and hand the dispatcher a tuple instead
            # of the model. Exceptions and list-of-results still use side_effect.
            failing_runtime.dispatch.return_value = side_effect
        else:
            failing_runtime.dispatch.side_effect = side_effect
        try:
            await dispatch(
                _STEP,
                runtime=failing_runtime,
                registry=_make_registry(),
                repo_root=repo_root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                sleep=_instant_sleep,
                _max_attempts=3,
            )
        except DispatchError:
            return None
        return None

    return _dispatch_fn


@pytest.mark.asyncio
async def test_cell1_positive_agent_failed_halts_loop(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(DispatchError("runtime unavailable")),
        state_path=state_path,
        max_iterations=1,
    )
    assert result.halted is True
    assert result.stop_reason == "agent_failed"
    stop_entries = [e for e in iter_entries(journal) if e.kind == "stop_triggered"]
    assert len(stop_entries) == 1
    assert stop_entries[0].payload["trigger"] == "agent_failed"
    assert "stop_trigger_raised" in _journal_kinds(journal)


@pytest.mark.asyncio
async def test_cell2_negative_fail_then_succeed_continues(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    side_effect = [
        DispatchError("fail 1"),
        DispatchError("fail 2"),
        AgentResult(output_text="ok", tokens_in=1, tokens_out=2),
    ]
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(side_effect),
        state_path=state_path,
        max_iterations=1,
    )
    assert result.halted is False
    assert result.stop_reason != "agent_failed"
    assert "stop_triggered" not in _journal_kinds(journal)
    assert "stop_trigger_raised" not in _journal_kinds(journal)
    # P1: prove the dispatcher actually retried twice then recovered, so a regression
    # where dispatch succeeds on the first call (ignoring the retry side-effects) would
    # not silently satisfy the "didn't halt" assertions above.
    attempt_outcomes = [
        e.payload.get("outcome") for e in iter_entries(journal) if e.kind == "dispatch_attempt"
    ]
    assert attempt_outcomes == ["retry", "retry", "success"]


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell3_termination_state_projection_reflects_halt(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(DispatchError("runtime unavailable")),
        state_path=state_path,
        max_iterations=1,
    )
    projected = project_from_journal(journal)
    assert projected.auto_loop_status == "halted"
    assert projected.stop_reason == "agent_failed"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="state rebuild is POSIX-only in v1")
async def test_cell4_resume_after_fix_check_and_loop_continue(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path)
    journal, runs, state_path = _bootstrap_journal(tmp_path)
    halted = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(DispatchError("runtime unavailable")),
        state_path=state_path,
        max_iterations=1,
    )
    assert halted.halted is True
    assert halted.stop_reason == "agent_failed"
    assert check_stop(repo_root=tmp_path, state=State()).fired is True

    success_side_effect = AgentResult(output_text="fixed", tokens_in=1, tokens_out=2)
    resumed = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_make_retry_dispatch_fn(success_side_effect),
        state_path=state_path,
        max_iterations=1,
    )
    assert resumed.halted is False
    assert resumed.stop_reason != "agent_failed"
    assert check_stop(repo_root=tmp_path, state=State()).fired is False

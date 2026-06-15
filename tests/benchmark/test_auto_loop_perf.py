"""Performance benchmark for auto-loop iteration overhead (NFR-PERF-6, Story 4.1)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from sdlc.engine.auto_loop import run_auto_loop
from sdlc.runtime.mock import MockAIRuntime
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="NFR-PERF-6 gate runs on Linux CI per AC3",
    ),
]

_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


def _bootstrap(tmp_path: Path) -> tuple[Path, Path, Path]:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    (tmp_path / "01-Requirement" / "04-Epics" / f"{_EPIC_ID}.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "01-Requirement" / "04-Epics" / f"{_EPIC_ID}.json").write_text(
        json.dumps({"id": _EPIC_ID}), encoding="utf-8"
    )
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
    for phase, rel in (
        (1, "01-Requirement/01-PRODUCT.md"),
        (2, "02-Architecture/ARCHITECTURE.md"),
    ):
        artifact_path = tmp_path / rel
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
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal = (state_dir / "journal.log").resolve()
    journal.touch()
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").resolve()
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    return tmp_path, journal, runs


def test_auto_loop_perf_one_iteration(benchmark: BenchmarkFixture, tmp_path: Path) -> None:
    root, journal, runs = _bootstrap(tmp_path)
    dispatch = AsyncMock(return_value=None)

    def run_one_iteration() -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                run_auto_loop(
                    root,
                    journal_path=journal,
                    agent_runs_path=runs,
                    runtime=_mock_runtime(tmp_path),
                    registry=SpecialistRegistry({}),
                    dispatch_fn=dispatch,
                    max_iterations=1,
                )
            )
        finally:
            loop.close()

    benchmark.pedantic(run_one_iteration, iterations=5, rounds=3, warmup_rounds=1)  # type: ignore[no-untyped-call]
    mean = benchmark.stats.stats.mean  # type: ignore[union-attr]
    assert mean < 1.0, f"auto-loop iteration overhead {mean:.3f}s exceeds 1.0s budget (NFR-PERF-6)"

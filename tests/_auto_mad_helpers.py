"""Shared fixtures for the mad-mode integration tests (Story 4.11).

Lives under ``tests/`` and is importable as ``from _auto_mad_helpers import ...``
(``tests/conftest.py`` puts ``tests/`` on ``sys.path``; same seam as ``_clihelper``).
Extracted from ``test_auto_mad.py`` to keep that module under the 400-LOC cap
(NFR-MAINT-3) and to dedup the project-seed helpers (CR4.11-W2): the signed and
unsigned variants are now one ``_write_phase3_ready_project(..., signed=...)``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

from sdlc.engine.next_selector import NextDecision
from sdlc.errors import DispatchError
from sdlc.runtime.mock import MockAIRuntime
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.specialists.registry import SpecialistRegistry

_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"
_TS = "2026-06-22T12:00:00.000Z"
_CLAR_ID = "clar-madtest01"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


def _options_md_body() -> str:
    return """# Clarification Options

## Option 1: Webhooks
### Pros
- Real-time updates
### Cons
- Requires public endpoint
### Risks
- Delivery retries

## Option 2: Polling
### Pros
- Simpler deployment
### Cons
- Higher latency
### Risks
- Rate-limit pressure
"""


def _write_approved_signoff(tmp_path: Path, phase: int, rel: str) -> None:
    artifact_path = tmp_path / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=phase,
            artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
            approved_by="human-test",
            approved_at=_TS,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_TS,
        ),
        repo_root=tmp_path,
    )


def _write_approved_signoffs(tmp_path: Path) -> None:
    for phase, rel in (
        (1, "01-Requirement/01-PRODUCT.md"),
        (2, "02-Architecture/ARCHITECTURE.md"),
    ):
        _write_approved_signoff(tmp_path, phase, rel)


def _write_phase3_ready_project(
    tmp_path: Path, *, stage: str = "pending", signed: bool = True
) -> None:
    """Seed a phase-3-ready project; ``signed`` controls whether phase 1/2 signoffs exist."""
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
    if signed:
        _write_approved_signoffs(tmp_path)


def _write_phase1_approved_phase2_unsigned_project(tmp_path: Path) -> None:
    _write_phase3_ready_project(tmp_path, signed=False)
    _write_approved_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")


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
        reason="integration test: force dispatch",
    )


def _seed_open_clarification(tmp_path: Path, *, with_options: bool = True) -> Path:
    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / _CLAR_ID
    clar_dir.mkdir(parents=True, exist_ok=True)
    open_path = clar_dir / "open_clarification.md"
    open_path.write_text(
        f"# Open Clarification\n\nclarification_id: {_CLAR_ID}\n\nPick one.\n",
        encoding="utf-8",
    )
    if with_options:
        (clar_dir / "options.md").write_text(_options_md_body(), encoding="utf-8")
    return open_path


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


def _make_retry_dispatch_fn(side_effect: object):
    from sdlc.contracts.workflow_spec import WorkflowSpec
    from sdlc.dispatcher.core import dispatch
    from sdlc.runtime.abc import AgentResult

    _step = WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent="product-strategist",
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={"product-strategist": ("docs/product.md",)},
    )

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
        from types import MappingProxyType

        from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
        from sdlc.specialists.frontmatter import Specialist

        _ = task_id, runtime, correlation_id
        specialist = Specialist(
            frontmatter=SpecialistFrontmatter(
                schema_version=1,
                name="product-strategist",
                title="Product Strategist",
                icon="📋",
                model="claude-opus-4-5",
                description="test",
                write_globs=("docs/product.md",),
            ),
            body="test",
            source_path=Path("product-strategist.md"),
        )
        reg = SpecialistRegistry(MappingProxyType({"product-strategist": specialist}))
        failing_runtime = AsyncMock()
        if isinstance(side_effect, AgentResult):
            failing_runtime.dispatch.return_value = side_effect
        else:
            failing_runtime.dispatch.side_effect = side_effect
        try:
            await dispatch(
                _step,
                runtime=failing_runtime,
                registry=reg,
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

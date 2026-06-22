"""Unit tests — engine/auto_loop.py mad-mode seam (Story 4.11).

Split from ``test_auto_loop.py`` to keep both modules under the 400-LOC cap
(NFR-MAINT-3). Shared project-seed fixtures live in ``tests/_auto_loop_helpers.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from _auto_loop_helpers import (
    _TASK_ID,
    _bootstrap_journal,
    _mock_runtime,
    _write_phase1_approved_phase2_unsigned_project,
    _write_phase3_ready_project,
)
from sdlc.engine.auto_loop import run_auto_loop
from sdlc.journal import iter_entries
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_mad_mode_resolves_signoff_required_and_continues(tmp_path: Path) -> None:
    from unittest.mock import patch

    from sdlc.engine.next_selector import NextDecision

    _write_phase1_approved_phase2_unsigned_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=NextDecision(
            kind="dispatch_task",
            task_id=_TASK_ID,
            phase=3,
            reason="unit: force dispatch",
        ),
    ):
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(return_value=None),
            max_iterations=1,
            mad_mode=True,
        )
    assert result.halted is False
    assert "stop_triggered" not in [e.kind for e in iter_entries(journal)]
    assert any(e.kind == "auto_mad_resolve" for e in iter_entries(journal))


@pytest.mark.asyncio
async def test_mad_mode_resolves_open_clarification_and_continues(tmp_path: Path) -> None:
    from unittest.mock import patch

    from sdlc.engine.next_selector import NextDecision

    _write_phase3_ready_project(tmp_path)
    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / "clar-loop"
    clar_dir.mkdir(parents=True)
    (clar_dir / "open_clarification.md").write_text("# open\n", encoding="utf-8")
    (clar_dir / "options.md").write_text(
        "## Option 1: A\n### Pros\n- a\n### Cons\n- b\n### Risks\n- c\n"
        "## Option 2: B\n### Pros\n- d\n### Cons\n- e\n### Risks\n- f\n",
        encoding="utf-8",
    )
    journal, runs = _bootstrap_journal(tmp_path)
    with patch(
        "sdlc.engine.auto_loop.resolve_next_action",
        return_value=NextDecision(
            kind="dispatch_task",
            task_id=_TASK_ID,
            phase=3,
            reason="unit: force dispatch",
        ),
    ):
        result = await run_auto_loop(
            tmp_path,
            journal_path=journal,
            agent_runs_path=runs,
            runtime=_mock_runtime(tmp_path),
            registry=SpecialistRegistry({}),
            dispatch_fn=AsyncMock(return_value=None),
            max_iterations=1,
            auto_brainstorm=False,
            mad_mode=True,
        )
    assert result.halted is False
    assert not (clar_dir / "open_clarification.md").exists()
    assert any(e.kind == "auto_mad_resolve" for e in iter_entries(journal))


@pytest.mark.asyncio
async def test_mad_mode_still_halts_on_agent_failed_unit(tmp_path: Path) -> None:
    import asyncio
    from types import MappingProxyType

    from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
    from sdlc.contracts.workflow_spec import WorkflowSpec
    from sdlc.dispatcher.core import dispatch
    from sdlc.errors import DispatchError
    from sdlc.specialists.frontmatter import Specialist

    async def _instant_sleep(seconds: float) -> None:
        await asyncio.sleep(0)

    _step = WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent="product-strategist",
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={"product-strategist": ("docs/product.md",)},
    )
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
    registry = SpecialistRegistry(MappingProxyType({"product-strategist": specialist}))

    async def _dispatch_fn(**kwargs) -> None:
        failing_runtime = AsyncMock()
        failing_runtime.dispatch.side_effect = DispatchError("runtime unavailable")
        try:
            await dispatch(
                _step,
                runtime=failing_runtime,
                registry=registry,
                repo_root=kwargs["repo_root"],
                journal_path=kwargs["journal_path"],
                agent_runs_path=kwargs["agent_runs_path"],
                sleep=_instant_sleep,
                _max_attempts=3,
            )
        except DispatchError:
            return None

    _write_phase3_ready_project(tmp_path)
    journal, runs = _bootstrap_journal(tmp_path)
    result = await run_auto_loop(
        tmp_path,
        journal_path=journal,
        agent_runs_path=runs,
        runtime=_mock_runtime(tmp_path),
        registry=SpecialistRegistry({}),
        dispatch_fn=_dispatch_fn,
        max_iterations=1,
        mad_mode=True,
    )
    assert result.halted is True
    assert result.stop_reason == "agent_failed"

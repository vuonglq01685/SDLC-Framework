"""Unit tests for dispatch_panel() terminal failure paths (Story 2A.3, AC5).

Terminal dispatch failures emit stop_trigger_raised journal entries.

TDD-first: tests committed before implementation (ADR-026 §1).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit

_PRIMARY = "product-strategist"
_PAR_A = "technical-researcher"
_PAR_B = "devil-advocate"
_SYNTH = "synthesizer"

_TARGET_PRIMARY = "docs/01-PRODUCT.md"
_TARGET_PAR_A = "docs/research.md"
_TARGET_PAR_B = "docs/critique.md"
_TARGET_SYNTH = _TARGET_PRIMARY  # synthesizer overwrites primary per AC2.4


def _make_spec(name: str, write_glob: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.replace("-", " ").title(),
        icon="📄",
        model="claude-opus-4-5",
        description=f"{name} specialist.",
        write_globs=(write_glob,),
    )
    return Specialist(frontmatter=fm, body=f"You are {name}.", source_path=Path(f"{name}.md"))


_PRIMARY_SPEC = _make_spec(_PRIMARY, _TARGET_PRIMARY)
_PAR_A_SPEC = _make_spec(_PAR_A, _TARGET_PAR_A)
_PAR_B_SPEC = _make_spec(_PAR_B, _TARGET_PAR_B)
_SYNTH_SPEC = _make_spec(_SYNTH, _TARGET_SYNTH)


def _make_registry(*specs: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specs}))


def _make_step(
    *,
    parallel: tuple[str, ...] = (),
    synth: str | None = None,
    extra_write_globs: dict | None = None,
) -> WorkflowSpec:
    wg: dict[str, tuple[str, ...]] = {_PRIMARY: (_TARGET_PRIMARY,)}
    for name, path in [(_PAR_A, _TARGET_PAR_A), (_PAR_B, _TARGET_PAR_B), (_SYNTH, _TARGET_SYNTH)]:
        if name in parallel or name == synth:
            wg[name] = (path,)
    if extra_write_globs:
        wg.update(extra_write_globs)
    return WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent=_PRIMARY,
        parallel_agents=parallel,
        synthesizer_agent=synth,
        write_globs=wg,
    )


class TestDispatchPanelMemberFailure:
    def test_panel_member_failure_returns_failed_outcome(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))
        runtime = AsyncMock()
        runtime.dispatch.side_effect = DispatchError("member failed after retries")
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                    _max_attempts=1,
                )
            )

        assert result.outcome == "failed"

    def test_panel_member_failure_synth_not_dispatched(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,), synth=_SYNTH)
        dispatched_agents: list[str] = []

        async def _mock_dispatch(prompt: str, context: dict) -> AgentResult:
            name = context.get("agent_name", "?")
            dispatched_agents.append(name)
            if name in (_PRIMARY, _PAR_A):
                raise DispatchError("member failed after retries")
            return AgentResult(output_text="synth out", tokens_in=5, tokens_out=10)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _mock_dispatch
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _SYNTH_SPEC)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                    _max_attempts=1,
                )
            )

        assert _SYNTH not in dispatched_agents

    def test_primary_failure_emits_stop_trigger_raised(self, tmp_path: Path) -> None:
        """Terminal primary failure → stop_trigger_raised journal entry (AC5)."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step()
        runtime = AsyncMock()
        runtime.dispatch.side_effect = DispatchError("primary failed")
        registry = _make_registry(_PRIMARY_SPEC)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                    _max_attempts=1,
                )
            )

        stop_entries = [e for e in captured if e.kind == "stop_trigger_raised"]
        assert len(stop_entries) == 1
        assert stop_entries[0].payload["trigger"] == "agent_failure_after_retries"
        assert stop_entries[0].payload["epic_4_placeholder"] is True
        assert stop_entries[0].payload["specialist"] == _PRIMARY

    def test_synth_failure_emits_stop_trigger_raised(self, tmp_path: Path) -> None:
        """Terminal synthesizer failure → stop_trigger_raised journal entry (AC5)."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(synth=_SYNTH)

        async def _dispatch(prompt: str, context: dict) -> AgentResult:
            if context.get("agent_name") == _SYNTH:
                raise DispatchError("synth failed")
            return AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _dispatch
        registry = _make_registry(_PRIMARY_SPEC, _SYNTH_SPEC)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                    _max_attempts=1,
                )
            )

        stop_entries = [e for e in captured if e.kind == "stop_trigger_raised"]
        assert len(stop_entries) == 1
        assert stop_entries[0].payload["specialist"] == _SYNTH
        assert stop_entries[0].payload["epic_4_placeholder"] is True

    def test_parallel_failure_emits_stop_trigger_raised(self, tmp_path: Path) -> None:
        """Parallel failure → stop_trigger_raised with specialist='parallel_agents' (AC5)."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))

        async def _dispatch(prompt: str, context: dict) -> AgentResult:
            if context.get("target_kind") == "parallel":
                raise DispatchError("parallel failed")
            return AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _dispatch
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                    _max_attempts=1,
                )
            )

        stop_entries = [e for e in captured if e.kind == "stop_trigger_raised"]
        assert len(stop_entries) == 1
        assert stop_entries[0].payload["specialist"] == "parallel_agents"
        assert stop_entries[0].payload["epic_4_placeholder"] is True

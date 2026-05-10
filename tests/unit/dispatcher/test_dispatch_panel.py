"""Unit tests for dispatcher.core.dispatch_panel() (Story 2A.3, AC2, Task 5.1).

TDD-first: tests committed before implementation (ADR-026 §1).

Journal writes and telemetry writes are mocked (POSIX-only in production).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch, call

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError, SpecialistError
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


class TestDispatchPanelPrimaryOnly:
    def test_primary_only_returns_panel_result(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step()
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="output", tokens_in=10, tokens_out=20)
        registry = _make_registry(_PRIMARY_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert result.outcome == "success"
        assert result.primary_result.specialist_name == _PRIMARY
        assert result.parallel_results == ()
        assert result.synthesizer_result is None

    def test_primary_only_one_runtime_dispatch_call(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step()
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="output", tokens_in=10, tokens_out=20)
        registry = _make_registry(_PRIMARY_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert runtime.dispatch.call_count == 1


class TestDispatchPanelWithParallel:
    def test_primary_plus_two_parallel_three_dispatch_calls(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B))
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="output", tokens_in=5, tokens_out=10)
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _PAR_B_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert runtime.dispatch.call_count == 3

    def test_parallel_results_in_panel_result(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B))
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="output", tokens_in=5, tokens_out=10)
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _PAR_B_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert len(result.parallel_results) == 2
        names = {r.specialist_name for r in result.parallel_results}
        assert names == {_PAR_A, _PAR_B}

    def test_each_member_writes_to_own_target(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))
        runtime = AsyncMock()
        runtime.dispatch.side_effect = [
            AgentResult(output_text="primary output", tokens_in=5, tokens_out=10),
            AgentResult(output_text="par_a output", tokens_in=5, tokens_out=10),
        ]
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        primary_file = tmp_path / _TARGET_PRIMARY
        par_a_file = tmp_path / _TARGET_PAR_A
        # Both files written to their own targets
        assert primary_file.exists()
        assert par_a_file.exists()


class TestDispatchPanelWithSynthesizer:
    def test_synth_dispatched_after_panel_completes(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B), synth=_SYNTH)
        call_order: list[str] = []

        async def _mock_dispatch(prompt: str, context: dict) -> AgentResult:
            call_order.append(context.get("agent_name", "?"))
            return AgentResult(output_text=f"output from {context.get('agent_name')}", tokens_in=5, tokens_out=10)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _mock_dispatch
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _PAR_B_SPEC, _SYNTH_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert result.synthesizer_result is not None
        assert result.synthesizer_result.specialist_name == _SYNTH
        # synth must come after panel members
        assert call_order.index(_SYNTH) > call_order.index(_PRIMARY)

    def test_synth_context_includes_panel_outputs(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,), synth=_SYNTH)
        captured_contexts: list[dict] = []

        async def _mock_dispatch(prompt: str, context: dict) -> AgentResult:
            captured_contexts.append(dict(context))
            return AgentResult(output_text="output", tokens_in=5, tokens_out=10)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _mock_dispatch
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _SYNTH_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        synth_context = next(c for c in captured_contexts if c.get("agent_name") == _SYNTH)
        assert synth_context["target_kind"] == "synthesizer"
        assert "panel_outputs" in synth_context
        assert _PRIMARY in synth_context["panel_outputs"]
        assert _PAR_A in synth_context["panel_outputs"]

    def test_synth_overwrites_primary_write_target(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,), synth=_SYNTH)
        runtime = AsyncMock()
        runtime.dispatch.side_effect = [
            AgentResult(output_text="primary output", tokens_in=5, tokens_out=10),
            AgentResult(output_text="par_a output", tokens_in=5, tokens_out=10),
            AgentResult(output_text="SYNTHESIZED", tokens_in=10, tokens_out=20),
        ]
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _SYNTH_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        primary_file = tmp_path / _TARGET_PRIMARY
        # Synth output overwrites primary's target (AC2.4 intentional)
        assert primary_file.read_text(encoding="utf-8") == "SYNTHESIZED"

    def test_four_agent_runs_lines_for_panel_with_synth(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A, _PAR_B), synth=_SYNTH)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="out", tokens_in=5, tokens_out=10)
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC, _PAR_B_SPEC, _SYNTH_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run") as mock_run,
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
                )
            )

        assert mock_run.call_count == 4  # primary + par_a + par_b + synth


class TestDispatchPanelMemberFailure:
    def test_panel_member_failure_returns_failed_outcome(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_step(parallel=(_PAR_A,))
        runtime = AsyncMock()
        runtime.dispatch.side_effect = DispatchError("member failed after retries")
        registry = _make_registry(_PRIMARY_SPEC, _PAR_A_SPEC)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
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
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=4,
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
            patch("sdlc.dispatcher.core.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
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
            patch("sdlc.dispatcher.core.journal_append", side_effect=_capture),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step, runtime=runtime, registry=registry,
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

"""Unit tests for dispatch_panel() concurrency contract (Story 2A.3, AC2, Task 5.2).

TDD-first: tests committed before implementation (ADR-026 §1).

Verifies:
- BoundedDispatcher is created with semaphore_size == max_parallel_agents
- With N parallel agents and max_parallel_agents=2, at most 2 dispatches execute at once
- parallel_results preserves input order (asyncio.gather ordering guarantee)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit

_PRIMARY = "primary-agent"
_PRIMARY_TARGET = "docs/primary.md"


def _make_spec(name: str, target: str) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name=name,
        title=name.replace("-", " ").title(),
        icon="📄",
        model="claude-opus-4-5",
        description=f"{name} specialist.",
        write_globs=(target,),
    )
    return Specialist(frontmatter=fm, body=f"You are {name}.", source_path=Path(f"{name}.md"))


_PRIMARY_SPEC = _make_spec(_PRIMARY, _PRIMARY_TARGET)


def _make_parallel_step(parallel_names: tuple[str, ...]) -> WorkflowSpec:
    write_globs: dict[str, tuple[str, ...]] = {_PRIMARY: (_PRIMARY_TARGET,)}
    for name in parallel_names:
        write_globs[name] = (f"docs/{name}.md",)
    return WorkflowSpec(
        schema_version=1,
        name="requirements",
        slash_command="sdlc-start",
        primary_agent=_PRIMARY,
        parallel_agents=parallel_names,
        synthesizer_agent=None,
        write_globs=write_globs,
    )


def _make_registry(*specs: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specs}))


class TestDispatchPanelBoundedDispatcher:
    def test_bounded_dispatcher_semaphore_matches_max_parallel_agents(
        self, tmp_path: Path
    ) -> None:
        """dispatch_panel passes max_parallel_agents as semaphore_size to BoundedDispatcher."""
        from sdlc.concurrency.subprocess_pool import BoundedDispatcher
        from sdlc.dispatcher.core import dispatch_panel

        parallel = ("par-a", "par-b")
        specs = [_make_spec(n, f"docs/{n}.md") for n in parallel]
        step = _make_parallel_step(parallel)
        registry = _make_registry(_PRIMARY_SPEC, *specs)

        captured_sizes: list[int] = []
        real_init = BoundedDispatcher.__init__

        def _capturing_init(self_: BoundedDispatcher, semaphore_size: int) -> None:
            captured_sizes.append(semaphore_size)
            real_init(self_, semaphore_size)

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="out", tokens_in=5, tokens_out=10
        )

        with (
            patch.object(BoundedDispatcher, "__init__", _capturing_init),
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=3,
                )
            )

        assert 3 in captured_sizes, (
            f"BoundedDispatcher not created with semaphore_size=3; captured: {captured_sizes}"
        )

    def test_semaphore_size_one_still_works(self, tmp_path: Path) -> None:
        """max_parallel_agents=1 serialises all parallel dispatches."""
        from sdlc.concurrency.subprocess_pool import BoundedDispatcher
        from sdlc.dispatcher.core import dispatch_panel

        parallel = ("par-a", "par-b", "par-c")
        specs = [_make_spec(n, f"docs/{n}.md") for n in parallel]
        step = _make_parallel_step(parallel)
        registry = _make_registry(_PRIMARY_SPEC, *specs)

        captured_sizes: list[int] = []
        real_init = BoundedDispatcher.__init__

        def _capturing_init(self_: BoundedDispatcher, semaphore_size: int) -> None:
            captured_sizes.append(semaphore_size)
            real_init(self_, semaphore_size)

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="out", tokens_in=5, tokens_out=10
        )

        with (
            patch.object(BoundedDispatcher, "__init__", _capturing_init),
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=1,
                )
            )

        assert 1 in captured_sizes


class TestDispatchPanelConcurrencyBound:
    def test_five_parallel_agents_max_two_in_flight(self, tmp_path: Path) -> None:
        """With max_parallel_agents=2 and 5 parallel agents, peak in-flight <= 2."""
        from sdlc.dispatcher.core import dispatch_panel

        parallel = tuple(f"agent-{i}" for i in range(5))
        specs = [_make_spec(n, f"docs/{n}.md") for n in parallel]
        step = _make_parallel_step(parallel)
        registry = _make_registry(_PRIMARY_SPEC, *specs)

        peak_in_flight = 0
        in_flight = 0

        async def _slow_dispatch(prompt: str, context: dict) -> AgentResult:
            nonlocal in_flight, peak_in_flight
            if context.get("target_kind") == "parallel":
                in_flight += 1
                peak_in_flight = max(peak_in_flight, in_flight)
                # Multiple yields so other tasks can enter the semaphore
                for _ in range(5):
                    await asyncio.sleep(0)
                in_flight -= 1
            return AgentResult(output_text="out", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _slow_dispatch

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch_panel(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    max_parallel_agents=2,
                )
            )

        assert peak_in_flight <= 2, (
            f"peak_in_flight={peak_in_flight} exceeded max_parallel_agents=2"
        )

    def test_primary_only_no_semaphore_constraint(self, tmp_path: Path) -> None:
        """Primary-only panel (no parallel agents) succeeds with any max_parallel_agents."""
        from sdlc.dispatcher.core import dispatch_panel

        step = _make_parallel_step(())  # no parallel agents
        registry = _make_registry(_PRIMARY_SPEC)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="out", tokens_in=5, tokens_out=10
        )

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
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
                )
            )

        assert result.outcome == "success"
        assert result.parallel_results == ()


class TestDispatchPanelResultOrder:
    def test_parallel_results_in_input_order(self, tmp_path: Path) -> None:
        """parallel_results preserves the order of parallel_agents in WorkflowSpec."""
        from sdlc.dispatcher.core import dispatch_panel

        # 4 parallel agents in a deliberate non-alphabetical order
        parallel = ("delta", "alpha", "gamma", "beta")
        specs = [_make_spec(n, f"docs/{n}.md") for n in parallel]
        step = _make_parallel_step(parallel)
        registry = _make_registry(_PRIMARY_SPEC, *specs)

        async def _dispatch_with_name(prompt: str, context: dict) -> AgentResult:
            return AgentResult(
                output_text=f"output:{context['agent_name']}",
                tokens_in=1,
                tokens_out=1,
            )

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _dispatch_with_name

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
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
                )
            )

        actual_order = tuple(r.specialist_name for r in result.parallel_results)
        assert actual_order == parallel, (
            f"Expected order {parallel!r}, got {actual_order!r}"
        )

    def test_single_parallel_agent_result_order(self, tmp_path: Path) -> None:
        """Single parallel agent produces parallel_results with exactly that agent."""
        from sdlc.dispatcher.core import dispatch_panel

        parallel = ("solo-agent",)
        specs = [_make_spec(n, f"docs/{n}.md") for n in parallel]
        step = _make_parallel_step(parallel)
        registry = _make_registry(_PRIMARY_SPEC, *specs)
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="out", tokens_in=1, tokens_out=1
        )

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
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
                )
            )

        assert len(result.parallel_results) == 1
        assert result.parallel_results[0].specialist_name == "solo-agent"

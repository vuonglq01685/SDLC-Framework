"""Unit tests for dispatcher.core.dispatch() primary-only path (Story 2A.3, AC1, AC8, Task 4.1).

TDD-first: tests committed before implementation (ADR-026 §1).

Journal writes are mocked (POSIX-only in production). Runtime is an AsyncMock.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import DispatchError, SpecialistError
from sdlc.runtime.abc import AgentResult
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

pytestmark = pytest.mark.unit

_SPECIALIST_NAME = "product-strategist"
_TARGET_REL = "01-Requirement/01-PRODUCT.md"

_FRONTMATTER = SpecialistFrontmatter(
    schema_version=1,
    name=_SPECIALIST_NAME,
    title="Product Strategist",
    icon="📋",
    model="claude-opus-4-5",
    description="Writes product requirements.",
    write_globs=(_TARGET_REL,),
)
_SPECIALIST = Specialist(
    frontmatter=_FRONTMATTER,
    body="You are a product strategist.",
    source_path=Path("specialists/product-strategist.md"),
)

_STEP = WorkflowSpec(
    schema_version=1,
    name="requirements",
    slash_command="sdlc-start",
    primary_agent=_SPECIALIST_NAME,
    parallel_agents=(),
    synthesizer_agent=None,
    write_globs={_SPECIALIST_NAME: (_TARGET_REL,)},
)

_AGENT_RESULT = AgentResult(output_text="# Product\n\nSpec content.", tokens_in=50, tokens_out=100)


def _make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


class TestDispatchPrimaryHappyPath:
    def test_returns_dispatch_result_with_success_outcome(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        assert result.outcome == "success"
        assert result.specialist_name == _SPECIALIST_NAME
        assert result.attempts == 1

    def test_runtime_dispatch_called_once_with_prompt_and_context(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        assert runtime.dispatch.call_count == 1
        ctx = runtime.dispatch.call_args[0][1]
        assert ctx["workflow_step"] == "requirements"
        assert ctx["agent_name"] == _SPECIALIST_NAME
        assert ctx["target_kind"] == "primary"

    def test_writes_output_to_target_path(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        target = result.target_path
        assert target.exists()
        assert target.read_text(encoding="utf-8") == _AGENT_RESULT.output_text

    def test_target_path_is_absolute_under_repo_root(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        assert result.target_path.is_absolute()
        assert result.target_path == tmp_path / _TARGET_REL

    def test_journal_append_called_twice(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock) as mock_append,
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        assert mock_append.call_count == 2

    def test_journal_contains_dispatch_attempt_kind(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock) as mock_append,
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        kinds = [c.args[0].kind for c in mock_append.call_args_list]
        assert "dispatch_attempt" in kinds

    def test_journal_contains_artifact_written_kind(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock) as mock_append,
            patch("sdlc.dispatcher.core.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        kinds = [c.args[0].kind for c in mock_append.call_args_list]
        assert "artifact_written" in kinds

    def test_record_agent_run_called_once(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = _AGENT_RESULT
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run") as mock_run,
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

        assert mock_run.call_count == 1
        _, kw = mock_run.call_args
        assert kw["specialist_name"] == _SPECIALIST_NAME
        assert kw["target_kind"] == "primary"
        assert kw["outcome"] == "success"
        assert kw["attempts"] == 1


class TestDispatchPrimaryErrorPaths:
    def test_missing_specialist_raises_specialist_error_unwrapped(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        registry = _make_registry()  # empty — no specialists

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
            pytest.raises(SpecialistError),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

    def test_missing_specialist_error_is_not_wrapped_in_dispatch_error(
        self, tmp_path: Path
    ) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        registry = _make_registry()

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
            pytest.raises(SpecialistError) as exc_info,
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )
        assert not isinstance(exc_info.value.__cause__, DispatchError), (
            "SpecialistError must NOT be wrapped in DispatchError"
        )

    def test_missing_write_globs_raises_dispatch_error(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        step_no_write_globs = WorkflowSpec(
            schema_version=1,
            name="requirements",
            slash_command="sdlc-start",
            primary_agent=_SPECIALIST_NAME,
            parallel_agents=(),
            synthesizer_agent=None,
            write_globs={},  # missing entry for specialist
        )
        runtime = AsyncMock()
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher.core.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher.core.record_agent_run"),
            pytest.raises(DispatchError, match="write_globs"),
        ):
            asyncio.run(
                dispatch(
                    step_no_write_globs,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                )
            )

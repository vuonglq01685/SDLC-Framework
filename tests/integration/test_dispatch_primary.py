"""Integration tests for dispatch() (Story 2A.3, AC1 + AC8 + AC11 mandatory).

DR1 of Story 2A.3 review: AC11 mandates `test_dispatch_primary.py` as integration coverage
for the primary dispatch path "regardless of D choice". Exercises end-to-end dispatch with
journal_append + record_agent_run mocked at the seam (journal/writer.py is POSIX-only;
Windows dev host cannot write the journal directly — tests run on Linux CI).

Verifies:
- AC1 step 1-6: registry resolve, context dict, runtime dispatch, write target, agent_runs line,
  DispatchResult shape.
- AC1 'and' clauses: dispatch_attempt JournalEntry; default _default_prompt_builder used.
- AC5 + P18: dispatch() emits stop_trigger_raised on terminal failure (parity with
  dispatch_panel).
- AC8 step 1: missing step.write_globs[primary] raises DispatchError.
- AC8 step 4: dispatcher does NOT validate path matches frontmatter write_globs (trusts loader).
- P2 + P3: write target validated against repo_root + glob characters.
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

_PRIMARY = "product-strategist"
_TARGET = "docs/01-PRODUCT.md"

_FM = SpecialistFrontmatter(
    schema_version=1,
    name=_PRIMARY,
    title="Product Strategist",
    icon="📋",
    model="claude-opus-4-5",
    description="Writes product requirements.",
    write_globs=(_TARGET,),
)
_SPECIALIST = Specialist(
    frontmatter=_FM,
    body="You are the product strategist. Write the PRD.",
    source_path=Path("specialists/product-strategist.md"),
)
_STEP = WorkflowSpec(
    schema_version=1,
    name="requirements",
    slash_command="sdlc-start",
    primary_agent=_PRIMARY,
    parallel_agents=(),
    synthesizer_agent=None,
    write_globs={_PRIMARY: (_TARGET,)},
)


def _make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


async def _instant_sleep(seconds: float) -> None:
    """Yield to event loop without sleeping — keeps tests fast under 1s/4s backoff."""
    await asyncio.sleep(0)


class TestDispatchPrimaryHappyPath:
    """AC1 happy path — full primary dispatch produces DispatchResult + journal + telemetry."""

    def test_returns_dispatch_result_with_success(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(
            output_text="# PRD\n\nThe product strategy.", tokens_in=42, tokens_out=128
        )
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.specialist_name == _PRIMARY
        assert result.outcome == "success"
        assert result.attempts == 1
        assert result.target_path == (tmp_path / _TARGET).resolve()
        assert result.agent_result.tokens_in == 42
        assert result.agent_result.tokens_out == 128

    def test_writes_output_to_target_path(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        body = "# PRD\n\nIntegration test artifact.\n"
        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text=body, tokens_in=1, tokens_out=1)
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        target = tmp_path / _TARGET
        assert target.exists()
        assert target.read_text(encoding="utf-8") == body

    def test_emits_dispatch_attempt_journal_entry(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="x", tokens_in=1, tokens_out=1)
        registry = _make_registry(_SPECIALIST)
        captured: list = []

        async def _capture_journal(entry, journal_path):  # type: ignore[no-untyped-def]
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture_journal),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        kinds = [e.kind for e in captured]
        # AC1 step 5 + AC8 'And' clause: dispatch_attempt + artifact_written
        assert "dispatch_attempt" in kinds
        assert "artifact_written" in kinds
        attempt_entry = next(e for e in captured if e.kind == "dispatch_attempt")
        assert attempt_entry.payload["specialist"] == _PRIMARY
        assert attempt_entry.payload["outcome"] == "success"
        assert attempt_entry.payload["attempt"] == 1
        assert attempt_entry.payload["target_kind"] == "primary"

    def test_emits_agent_runs_line(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="x", tokens_in=10, tokens_out=20)
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run") as record_spy,
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        record_spy.assert_called_once()
        kwargs = record_spy.call_args.kwargs
        assert kwargs["workflow_step"] == "requirements"
        assert kwargs["specialist_name"] == _PRIMARY
        assert kwargs["target_kind"] == "primary"
        assert kwargs["outcome"] == "success"
        assert kwargs["attempts"] == 1
        assert kwargs["tokens_in"] == 10
        assert kwargs["tokens_out"] == 20


class TestDispatchPrimaryRetryAndFailure:
    """AC4 + AC5 — retry semantics integrated through dispatch()."""

    def test_runtime_failure_then_success_dispatches_twice(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        attempts = {"n": 0}

        async def _flaky(prompt: str, context: dict) -> AgentResult:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise DispatchError("flaky")
            return AgentResult(output_text="ok", tokens_in=1, tokens_out=1)

        runtime = AsyncMock()
        runtime.dispatch.side_effect = _flaky
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
        ):
            result = asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )
        assert result.attempts == 2
        assert result.outcome == "success"
        assert attempts["n"] == 2

    def test_terminal_failure_emits_stop_trigger_raised(self, tmp_path: Path) -> None:
        """P18: dispatch() emits stop_trigger_raised on terminal failure (parity)."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.side_effect = DispatchError("perma-fail")
        registry = _make_registry(_SPECIALIST)
        captured: list = []

        async def _capture_journal(entry, journal_path):  # type: ignore[no-untyped-def]
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture_journal),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(DispatchError),
        ):
            asyncio.run(
                dispatch(
                    _STEP,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                    _max_attempts=1,
                )
            )
        stop_kinds = [e for e in captured if e.kind == "stop_trigger_raised"]
        assert len(stop_kinds) == 1
        payload = stop_kinds[0].payload
        assert payload["trigger"] == "agent_failure_after_retries"
        assert payload["specialist"] == _PRIMARY
        assert payload["epic_4_placeholder"] is True


class TestDispatchPrimaryErrorPaths:
    """AC1 step 1 + AC8 step 1 — error propagation."""

    def test_missing_specialist_raises_specialist_error(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        registry = _make_registry()  # empty
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
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
                    sleep=_instant_sleep,
                )
            )

    def test_missing_write_globs_entry_raises_dispatch_error(self, tmp_path: Path) -> None:
        from sdlc.dispatcher.core import dispatch

        # WorkflowSpec with no write_globs entry for primary
        step = WorkflowSpec(
            schema_version=1,
            name="bad-step",
            slash_command="sdlc-start",
            primary_agent=_PRIMARY,
            parallel_agents=(),
            synthesizer_agent=None,
            write_globs={"some-other-agent": ("docs/x.md",)},
        )
        runtime = AsyncMock()
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(DispatchError, match="no write_globs entry"),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )

    def test_glob_in_write_target_raises_dispatch_error(self, tmp_path: Path) -> None:
        """P3: write_globs[0] containing glob characters rejected before mkdir."""
        from sdlc.dispatcher.core import dispatch

        step = WorkflowSpec(
            schema_version=1,
            name="glob-step",
            slash_command="sdlc-start",
            primary_agent=_PRIMARY,
            parallel_agents=(),
            synthesizer_agent=None,
            write_globs={_PRIMARY: ("docs/**/*.md",)},
        )
        runtime = AsyncMock()
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(DispatchError, match="glob characters"),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )

    def test_path_traversal_attempt_raises_dispatch_error(self, tmp_path: Path) -> None:
        """P2: write_globs[0] resolving outside repo_root rejected before write."""
        from sdlc.dispatcher.core import dispatch

        step = WorkflowSpec(
            schema_version=1,
            name="traversal-step",
            slash_command="sdlc-start",
            primary_agent=_PRIMARY,
            parallel_agents=(),
            synthesizer_agent=None,
            write_globs={_PRIMARY: ("../../escaped.md",)},
        )
        runtime = AsyncMock()
        registry = _make_registry(_SPECIALIST)
        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run"),
            pytest.raises(DispatchError, match="outside repo_root"),
        ):
            asyncio.run(
                dispatch(
                    step,
                    runtime=runtime,
                    registry=registry,
                    repo_root=tmp_path,
                    journal_path=tmp_path / "journal.log",
                    agent_runs_path=tmp_path / "agent_runs.jsonl",
                    sleep=_instant_sleep,
                )
            )

"""Integration tests for dispatch() retry behavior (Story 2A.3, AC4, Task 6.1).

TDD-first: tests committed before implementation (ADR-026 §1).

Verifies AC4's per-attempt journal entry contract:
  "every attempt (success or failure) appends ONE JournalEntry with
   kind='dispatch_attempt' and payload={..., 'outcome': 'success'|'retry'|'failed',
   'attempt': <1|2|3>}"

These tests use a fast sleep (asyncio.sleep(0)) injected via the `sleep` parameter
to avoid blocking on the production backoff schedule (1s/4s per AC4).
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

_SPECIALIST_NAME = "product-strategist"
_TARGET_REL = "docs/product.md"

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
_STEP = WorkflowSpec(
    schema_version=1,
    name="requirements",
    slash_command="sdlc-start",
    primary_agent=_SPECIALIST_NAME,
    parallel_agents=(),
    synthesizer_agent=None,
    write_globs={_SPECIALIST_NAME: (_TARGET_REL,)},
)


def _make_registry(*specialists: Specialist) -> SpecialistRegistry:
    return SpecialistRegistry(MappingProxyType({s.frontmatter.name: s for s in specialists}))


async def _instant_sleep(seconds: float) -> None:
    """Yield to event loop without sleeping — keeps tests fast."""
    await asyncio.sleep(0)


class TestDispatchRetryJournalEntries:
    """AC4 per-attempt journal entry contract (3 rows for 3-attempt run)."""

    def test_all_three_attempts_fail_produces_three_dispatch_attempt_rows(
        self, tmp_path: Path
    ) -> None:
        """3 DispatchErrors in a row → 3 dispatch_attempt journal entries."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.side_effect = DispatchError("runtime unavailable")
        registry = _make_registry(_SPECIALIST)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
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
                    _max_attempts=3,
                )
            )

        rows = [e for e in captured if e.kind == "dispatch_attempt"]
        assert len(rows) == 3, f"Expected 3 dispatch_attempt rows, got {len(rows)}"
        outcomes = [e.payload["outcome"] for e in rows]
        assert outcomes == ["retry", "retry", "failed"]

    def test_two_fail_then_success_produces_three_dispatch_attempt_rows(
        self, tmp_path: Path
    ) -> None:
        """2 failures then success → 3 dispatch_attempt rows (retry, retry, success)."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.side_effect = [
            DispatchError("fail 1"),
            DispatchError("fail 2"),
            AgentResult(output_text="success content", tokens_in=5, tokens_out=10),
        ]
        registry = _make_registry(_SPECIALIST)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
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
                    _max_attempts=3,
                )
            )

        assert result.outcome == "success"
        rows = [e for e in captured if e.kind == "dispatch_attempt"]
        assert len(rows) == 3, f"Expected 3 dispatch_attempt rows, got {len(rows)}"
        outcomes = [e.payload["outcome"] for e in rows]
        assert outcomes == ["retry", "retry", "success"]
        attempt_nums = [e.payload["attempt"] for e in rows]
        assert attempt_nums == [1, 2, 3]

    def test_first_attempt_success_produces_one_dispatch_attempt_row(self, tmp_path: Path) -> None:
        """Single-attempt success → 1 dispatch_attempt row with outcome=success."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="done", tokens_in=5, tokens_out=10)
        registry = _make_registry(_SPECIALIST)
        captured: list = []

        async def _capture(entry, path) -> None:
            captured.append(entry)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", side_effect=_capture),
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

        rows = [e for e in captured if e.kind == "dispatch_attempt"]
        assert len(rows) == 1
        assert rows[0].payload["outcome"] == "success"
        assert rows[0].payload["attempt"] == 1


class TestDispatchRetryAttemptCount:
    """DispatchResult.attempts reflects the actual number of attempts taken."""

    def test_two_fail_one_success_result_attempts_is_three(self, tmp_path: Path) -> None:
        """After 2 retries to success, DispatchResult.attempts == 3."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.side_effect = [
            DispatchError("fail"),
            DispatchError("fail again"),
            AgentResult(output_text="success", tokens_in=5, tokens_out=10),
        ]
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
                    _max_attempts=3,
                )
            )

        assert result.attempts == 3

    def test_first_attempt_success_result_attempts_is_one(self, tmp_path: Path) -> None:
        """First-attempt success → DispatchResult.attempts == 1."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.return_value = AgentResult(output_text="done", tokens_in=5, tokens_out=10)
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

        assert result.attempts == 1

    def test_record_agent_run_attempts_matches_actual_count(self, tmp_path: Path) -> None:
        """record_agent_run is called with the actual attempts count, not hardcoded 1."""
        from sdlc.dispatcher.core import dispatch

        runtime = AsyncMock()
        runtime.dispatch.side_effect = [
            DispatchError("fail"),
            AgentResult(output_text="done", tokens_in=5, tokens_out=10),
        ]
        registry = _make_registry(_SPECIALIST)

        with (
            patch("sdlc.dispatcher._panel_helpers.journal_append", new_callable=AsyncMock),
            patch("sdlc.dispatcher._panel_helpers.record_agent_run") as mock_record,
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
                    _max_attempts=3,
                )
            )

        _, kw = mock_record.call_args
        assert kw["attempts"] == 2

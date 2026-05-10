"""Unit tests for DispatchResult dataclass shape (Story 2A.3, AC1, Task 4.2).

TDD-first: tests committed before implementation (ADR-026 §1).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from sdlc.runtime.abc import AgentResult

pytestmark = pytest.mark.unit

_AGENT_RESULT = AgentResult(output_text="done", tokens_in=10, tokens_out=20)


class TestDispatchResultShape:
    def test_is_frozen_dataclass(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        assert dataclasses.is_dataclass(DispatchResult)
        fields = {f.name for f in dataclasses.fields(DispatchResult)}
        assert "specialist_name" in fields
        assert "target_path" in fields
        assert "agent_result" in fields
        assert "attempts" in fields
        assert "outcome" in fields

    def test_construction_succeeds_with_all_fields(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        result = DispatchResult(
            specialist_name="product-strategist",
            target_path=Path("01-Requirement/01-PRODUCT.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        assert result.specialist_name == "product-strategist"
        assert result.target_path == Path("01-Requirement/01-PRODUCT.md")
        assert result.agent_result is _AGENT_RESULT
        assert result.attempts == 1
        assert result.outcome == "success"

    def test_outcome_success_and_failed_accepted(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        r_ok = DispatchResult(
            specialist_name="s",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        r_fail = DispatchResult(
            specialist_name="s",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=3,
            outcome="failed",
        )
        assert r_ok.outcome == "success"
        assert r_fail.outcome == "failed"


class TestDispatchResultImmutability:
    def test_mutation_raises_frozen_instance_error(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        result = DispatchResult(
            specialist_name="s",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.specialist_name = "other"  # type: ignore[misc]

    def test_equal_results_compare_equal(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        r1 = DispatchResult(
            specialist_name="s",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        r2 = DispatchResult(
            specialist_name="s",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        assert r1 == r2

    def test_different_results_not_equal(self) -> None:
        from sdlc.dispatcher.core import DispatchResult

        r1 = DispatchResult(
            specialist_name="a",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        r2 = DispatchResult(
            specialist_name="b",
            target_path=Path("x.md"),
            agent_result=_AGENT_RESULT,
            attempts=1,
            outcome="success",
        )
        assert r1 != r2

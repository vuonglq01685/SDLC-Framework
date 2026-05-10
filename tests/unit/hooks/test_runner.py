"""Tests for hooks/runner.py — HookDecision + run_hook_chain (AC3, Story 2A.4 Task 2)."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.errors import HookError
from sdlc.hooks.runner import HookDecision, run_hook_chain


def _payload() -> HookPayload:
    return HookPayload(
        hook_name="test_hook",
        target_path="01-Requirement/04-Epics/EPIC-stripe-webhook.json",
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="create epic JSON",
    )


@pytest.mark.unit
class TestHookDecision:
    def test_allow_factory(self) -> None:
        d = HookDecision.allow()
        assert d.decision == "allow"
        assert d.hook_name is None
        assert d.reason is None
        assert d.error_code is None

    def test_deny_factory(self) -> None:
        d = HookDecision.deny(
            hook_name="naming_validator",
            reason="bad name",
            error_code="naming_violation",
        )
        assert d.decision == "deny"
        assert d.hook_name == "naming_validator"
        assert d.reason == "bad name"
        assert d.error_code == "naming_violation"

    def test_frozen_mutation_raises(self) -> None:
        d = HookDecision.allow()
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.decision = "deny"  # type: ignore[misc]

    def test_deny_requires_reason(self) -> None:
        with pytest.raises(TypeError):
            HookDecision.deny(hook_name="h", error_code="naming_violation")  # type: ignore[call-arg]

    def test_deny_requires_error_code(self) -> None:
        with pytest.raises(TypeError):
            HookDecision.deny(hook_name="h", reason="r")  # type: ignore[call-arg]


@pytest.mark.unit
class TestRunHookChain:
    async def test_empty_hooks_returns_allow(self) -> None:
        result = await run_hook_chain(_payload(), hooks=(), journal_path=None)
        assert result == HookDecision.allow()

    async def test_single_allow_hook_no_journal(self) -> None:
        def allow_hook(p: HookPayload) -> HookDecision:
            return HookDecision.allow()

        with patch("sdlc.journal.append", new_callable=AsyncMock) as mock_append:
            result = await run_hook_chain(_payload(), hooks=(allow_hook,), journal_path=None)
            assert result.decision == "allow"
            mock_append.assert_not_called()

    async def test_single_deny_hook_returns_deny(self) -> None:
        def deny_hook(p: HookPayload) -> HookDecision:
            return HookDecision.deny(
                hook_name="naming_validator",
                reason="bad name",
                error_code="naming_violation",
            )

        with patch("sdlc.journal.append", new_callable=AsyncMock) as mock_append:
            result = await run_hook_chain(_payload(), hooks=(deny_hook,), journal_path=None)
            assert result.decision == "deny"
            assert result.hook_name == "naming_validator"
            # no journal when path is None
            mock_append.assert_not_called()

    async def test_deny_short_circuits_downstream(self) -> None:
        """Task 2.3 anti-tautology: deny stops chain; downstream allow NOT invoked."""
        downstream_called = []

        def deny_hook(p: HookPayload) -> HookDecision:
            return HookDecision.deny(
                hook_name="naming_validator",
                reason="bad name",
                error_code="naming_violation",
            )

        def downstream_hook(p: HookPayload) -> HookDecision:
            downstream_called.append(True)
            return HookDecision.allow()

        with patch("sdlc.journal.append", new_callable=AsyncMock):
            result = await run_hook_chain(
                _payload(), hooks=(deny_hook, downstream_hook), journal_path=None
            )
        assert result.decision == "deny"
        assert downstream_called == []  # downstream was NOT invoked

    async def test_hook_error_converted_to_deny(self) -> None:
        def error_hook(p: HookPayload) -> HookDecision:
            raise HookError("hook crashed", details={"step": "test"})

        with patch("sdlc.journal.append", new_callable=AsyncMock):
            result = await run_hook_chain(_payload(), hooks=(error_hook,), journal_path=None)
        assert result.decision == "deny"
        assert result.error_code == "hook_internal_error"

    async def test_non_sdlc_error_propagates(self) -> None:
        def bad_hook(p: HookPayload) -> HookDecision:
            raise ValueError("unexpected crash")

        with (
            patch("sdlc.journal.append", new_callable=AsyncMock),
            pytest.raises(ValueError, match="unexpected crash"),
        ):
            await run_hook_chain(_payload(), hooks=(bad_hook,), journal_path=None)

    async def test_deny_appends_journal_when_path_given(self, tmp_path) -> None:
        """When journal_path is given, deny appends one journal entry."""

        def deny_hook(p: HookPayload) -> HookDecision:
            return HookDecision.deny(
                hook_name="naming_validator",
                reason="bad name",
                error_code="naming_violation",
            )

        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            await run_hook_chain(_payload(), hooks=(deny_hook,), journal_path=journal_path)
            mock_j.assert_called_once()
            call_args = mock_j.call_args
            entry = call_args.args[0]
            assert entry.kind == "hook_rejected"
            assert entry.payload["hook"] == "naming_validator"
            assert entry.payload["error_code"] == "naming_violation"

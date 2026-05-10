"""Integration smoke tests for the hook chain (AC7, Story 2A.4 Task 8.1).

Exercises the runner end-to-end: dispatcher-shaped caller → run_hook_chain →
assert allow/deny/journal entry outcomes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain


def _make_phase_gate(repo_root: Path):
    def _hook(p: HookPayload) -> HookDecision:
        # Smoke tests only exercise Phase-1 paths or bypass; reader is never called.
        return phase_gate(
            p,
            repo_root=repo_root,
            signoff_reader=lambda ph, rr: "awaiting-signoff",
        )

    return _hook


@pytest.mark.integration
class TestHookChainSmoke:
    async def test_allow_path_no_journal(self, tmp_path) -> None:
        """Valid epic path, no signoff needed → chain allows, no journal entry."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-stripe-webhook.json",
            write_intent="create epic JSON",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                journal_path=None,
            )
        assert result.decision == "allow"
        mock_j.assert_not_called()

    async def test_deny_path_naming_violation(self, tmp_path) -> None:
        """Malformed epic id → chain denies, journal entry recorded."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPC_typo.json",
            write_intent="create epic JSON",
        )
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                journal_path=journal_path,
            )
        assert result.decision == "deny"
        assert result.error_code == "naming_violation"
        mock_j.assert_called_once()
        entry = mock_j.call_args.args[0]
        assert entry.kind == "hook_rejected"

    async def test_bypass_path_phase_gate_bypassed(self, tmp_path) -> None:
        """phase_gate bypassed for Phase 2 path with no signoff when bypass=True."""
        payload = build_write_intent_payload(
            hook_name="phase_gate",
            target_path="02-Architecture/01-UX/01-tokens.md",
            write_intent="update tokens",
        )
        journal_path = tmp_path / "journal.log"
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                bypass_phase_gate=True,
                justification="emergency hotfix needed",
                journal_path=journal_path,
            )
        assert result.decision == "allow"
        # bypass_signoff journal entry must be present
        calls = [c for c in mock_j.call_args_list if c.args[0].kind == "bypass_signoff"]
        assert len(calls) == 1


@pytest.mark.integration
class TestHookChainIntegrationMap:
    """Integration contract tests per AC7 — the contract Story 2A.6 wiring will conform to."""

    async def test_payload_construction_roundtrip(self, tmp_path) -> None:
        """Dispatcher-shaped caller builds payload → runs chain → asserts outcome."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-foo-bar.json",
            write_intent="create epic",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, _make_phase_gate(tmp_path)),
                journal_path=None,
            )
        assert result.decision == "allow"

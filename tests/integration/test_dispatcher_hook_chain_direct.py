"""Direct ``run_hook_chain`` tests split from hook-dispatcher integration (LOC §765).

Migrated from ``test_hook_chain_smoke.py`` (Story 2A.4 Task 8.1). Covers
``journal_path=None`` (no journal append) and payload roundtrip — not exercised
via ``dispatch()``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import run_hook_chain

from .dispatcher_hook_helpers import phase_gate_hook


@pytest.mark.integration
class TestRunHookChainDirect:
    """Direct run_hook_chain tests (AC7, 2A.4 Task 8.1)."""

    async def test_allow_path_no_journal(self, tmp_path: Path) -> None:
        """Valid epic path, journal_path=None → chain allows, _do_journal_append NOT called."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-stripe-webhook.json",
            write_intent="create epic JSON",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock) as mock_j:
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, phase_gate_hook(tmp_path)),
                journal_path=None,
            )
        assert result.decision == "allow"
        mock_j.assert_not_called()

    async def test_payload_construction_roundtrip(self, tmp_path: Path) -> None:
        """build_write_intent_payload → run_hook_chain → allow for a valid phase-1 epic path."""
        payload = build_write_intent_payload(
            hook_name="naming_validator",
            target_path="01-Requirement/04-Epics/EPIC-foo-bar.json",
            write_intent="create epic",
        )
        with patch("sdlc.hooks.runner._do_journal_append", new_callable=AsyncMock):
            result = await run_hook_chain(
                payload,
                hooks=(naming_validator, phase_gate_hook(tmp_path)),
                journal_path=None,
            )
        assert result.decision == "allow"

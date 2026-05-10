"""Unit tests for _to_claude_envelope() (AC4, Story 2A.6 Task 2.3).

Tests are RED until Task 2.4 ships ``src/sdlc/claude_hooks/pre_tool_use.py``.

Coverage target: the 4-line translation function asserted in both directions
(allow → approve, deny → block) plus error_code round-trip.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestToClaudeEnvelopeAllow:
    def test_allow_decision_maps_to_approve(self) -> None:
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {"decision": "allow", "hook_name": None, "reason": None, "error_code": None}
        result = _to_claude_envelope(engine)
        assert result["decision"] == "approve"

    def test_allow_reason_is_none(self) -> None:
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {"decision": "allow", "hook_name": None, "reason": None, "error_code": None}
        result = _to_claude_envelope(engine)
        assert result.get("reason") is None

    def test_allow_envelope_error_code_is_none(self) -> None:
        """DR3 → D1: AC2 canonical 4-key shape — allow envelope includes error_code=None."""
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {"decision": "allow", "hook_name": None, "reason": None, "error_code": None}
        result = _to_claude_envelope(engine)
        assert "error_code" in result
        assert result["error_code"] is None
        # All 4 canonical keys present.
        assert set(result.keys()) == {"decision", "hook_name", "reason", "error_code"}


@pytest.mark.unit
class TestToClaudeEnvelopeDeny:
    def test_deny_decision_maps_to_block(self) -> None:
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {
            "decision": "deny",
            "hook_name": "naming_validator",
            "reason": "naming violation",
            "error_code": "naming_violation",
        }
        result = _to_claude_envelope(engine)
        assert result["decision"] == "block"

    def test_deny_reason_preserved(self) -> None:
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {
            "decision": "deny",
            "hook_name": "naming_validator",
            "reason": "naming violation: 'EPC_typo' does not match epic id regex",
            "error_code": "naming_violation",
        }
        result = _to_claude_envelope(engine)
        assert "naming violation" in (result.get("reason") or "")

    def test_deny_error_code_round_trip(self) -> None:
        """error_code preserved from engine deny → Claude block envelope."""
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {
            "decision": "deny",
            "hook_name": "phase_gate",
            "reason": "phase-gate violation",
            "error_code": "phase_gate_violation",
        }
        result = _to_claude_envelope(engine)
        assert result.get("error_code") == "phase_gate_violation"

    def test_deny_envelope_contains_block_not_deny(self) -> None:
        """Engine uses 'deny'; Claude envelope uses 'block' (AC4 field-name mapping)."""
        from sdlc.claude_hooks.pre_tool_use import _to_claude_envelope

        engine = {
            "decision": "deny",
            "hook_name": "naming_validator",
            "reason": "bad name",
            "error_code": "naming_violation",
        }
        result = _to_claude_envelope(engine)
        assert result["decision"] != "deny"
        assert result["decision"] == "block"

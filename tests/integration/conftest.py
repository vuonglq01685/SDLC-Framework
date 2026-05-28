"""Integration-test session hooks (Story 2B.3 cross-runtime assertion)."""

from __future__ import annotations

import pytest

from integration._abstraction_adequacy_capture import pop_captured
from integration._abstraction_adequacy_helpers import _format_diff


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """After all parametrized conformance runs, assert mock and claude bytes match."""
    del session, exitstatus
    captured = pop_captured()
    if not captured:
        return
    if "mock_factory" not in captured or "claude_factory" not in captured:
        return
    mock_hp, mock_state = captured["mock_factory"]
    claude_hp, claude_state = captured["claude_factory"]
    assert mock_hp == claude_hp, _format_diff("hook payloads (mock vs claude)", mock_hp, claude_hp)
    assert mock_state == claude_state, _format_diff(
        "state.json (mock vs claude)", mock_state, claude_state
    )

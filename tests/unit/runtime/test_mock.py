"""Runtime model parity tests (Story 1.21, deferred-work Item D)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.unit
def test_fixture_and_agent_result_have_parity_fields() -> None:
    """Mock runtime's _Fixture and abc's AgentResult must share the same field set
    (otherwise mock and real Claude diverge silently). NOT a wire-format contract
    — see ADR-024 'Excluded from the lock' for the boundary rationale."""
    from sdlc.runtime.abc import AgentResult
    from sdlc.runtime.mock import _Fixture  # deliberate: parity test coupling is acceptable

    assert frozenset(_Fixture.model_fields) == frozenset(AgentResult.model_fields)

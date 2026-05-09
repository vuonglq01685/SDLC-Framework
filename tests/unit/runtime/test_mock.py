"""Runtime model parity tests (Story 1.21, deferred-work Item D)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _field_signature(model_cls: type) -> frozenset[tuple[str, object, bool]]:
    """Return a frozenset of (name, annotation, is_required) tuples for a pydantic model.

    Comparing this signature (rather than just `frozenset(model_fields)`) catches
    rename-equivalent type drift between `_Fixture` and `AgentResult` — e.g. a
    `tokens_in: int` → `tokens_in: float` change passes a names-only comparison
    vacuously even though the wire shape has shifted.
    """
    return frozenset(
        (name, field_info.annotation, field_info.is_required())
        for name, field_info in model_cls.model_fields.items()
    )


@pytest.mark.unit
def test_fixture_and_agent_result_have_parity_fields() -> None:
    """Mock runtime's _Fixture and abc's AgentResult must share the same field set
    (otherwise mock and real Claude diverge silently). NOT a wire-format contract
    — see ADR-024 'Excluded from the lock' for the boundary rationale.

    Compares (name, annotation, is_required) tuples, not just names — so a type or
    requirement drift fails the assertion (P24).
    """
    from sdlc.runtime.abc import AgentResult
    from sdlc.runtime.mock import _Fixture  # deliberate: parity test coupling is acceptable

    fixture_sig = _field_signature(_Fixture)
    agent_result_sig = _field_signature(AgentResult)
    assert fixture_sig == agent_result_sig, (
        f"_Fixture and AgentResult diverged:\n"
        f"  _Fixture only:    {fixture_sig - agent_result_sig}\n"
        f"  AgentResult only: {agent_result_sig - fixture_sig}\n"
        f"action: keep the two field-sets in lockstep "
        f"(mock fixture must match the public dispatch result)."
    )

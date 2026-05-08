"""Unit tests for the State Pydantic model — cross-platform (Story 1.10)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_state_defaults() -> None:
    from sdlc.state.model import State

    s = State()
    assert s.schema_version == 1
    assert s.next_monotonic_seq == 0
    assert s.epics == {}


def test_state_construction() -> None:
    from sdlc.state.model import State

    s = State(schema_version=1, next_monotonic_seq=42, epics={"e1": {"x": 1}})
    assert s.schema_version == 1
    assert s.next_monotonic_seq == 42
    assert s.epics == {"e1": {"x": 1}}


def test_state_frozen_immutable() -> None:
    from pydantic import ValidationError

    from sdlc.state.model import State

    s = State(next_monotonic_seq=5)
    with pytest.raises((ValidationError, TypeError)):
        s.next_monotonic_seq = 99  # type: ignore[misc]


def test_state_extra_forbidden() -> None:
    from pydantic import ValidationError

    from sdlc.state.model import State

    with pytest.raises(ValidationError, match="extra"):
        State(unknown_field=True)  # type: ignore[call-arg]


def test_state_equality() -> None:
    from sdlc.state.model import State

    a = State(next_monotonic_seq=7)
    b = State(next_monotonic_seq=7)
    assert a == b


def test_state_inequality() -> None:
    from sdlc.state.model import State

    a = State(next_monotonic_seq=1)
    b = State(next_monotonic_seq=2)
    assert a != b

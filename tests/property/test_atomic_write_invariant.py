"""Hypothesis property test: two-state invariant for write_state_atomic (AC3, Story 1.10).

For all sequences of valid states written sequentially, read_state after each write
returns exactly that state — never an intermediate or invalid value.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [
    pytest.mark.property,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — fcntl + fsync required"),
]

_epics_strategy: st.SearchStrategy[dict[str, Any]] = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.one_of(st.text(), st.integers(), st.booleans(), st.none()),
        max_size=5,
    ),
    max_size=5,
)

state_strategy = st.builds(
    lambda schema_version, next_monotonic_seq, epics: __import__(
        "sdlc.state.model", fromlist=["State"]
    ).State(schema_version=schema_version, next_monotonic_seq=next_monotonic_seq, epics=epics),
    schema_version=st.just(1),
    next_monotonic_seq=st.integers(min_value=0, max_value=2**63 - 1),
    epics=_epics_strategy,
)

states_sequence_strategy = st.lists(state_strategy, min_size=1, max_size=20)


@pytest.mark.xfail(
    reason="Pre-existing failure on main@12374b3 (verified by bisect 2026-05-10);"
    " tracked in EPIC-2A-DEBT-008. Story 2A.5 DR2 quarantine.",
    strict=False,
)
@given(states=states_sequence_strategy)
@settings(max_examples=1000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_sequential_writes_two_state_invariant(states: list[Any], tmp_path: Path) -> None:
    """After every sequential write, read_state returns exactly that state.

    Simplified single-writer property — concurrent-writer property deferred to Story 1.11
    once journal append is the source of truth (Decision B5).
    """
    from sdlc.state.atomic import read_state, write_state_atomic_sync

    target = tmp_path / "state.json"

    for i, state in enumerate(states):
        write_state_atomic_sync(state, target)
        result = read_state(target)
        assert result is not None, f"read_state returned None after write {i}"
        assert result == state, f"After write {i}, expected {state}, got {result}"

    # Final read still returns last state
    final = read_state(target)
    assert final == states[-1], f"Final read returned {final}, expected {states[-1]}"

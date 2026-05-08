"""Tests for read_state round-trip and error paths (AC1, Story 1.10)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — atomic.py requires POSIX"),
]


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


def test_round_trip(target: Path) -> None:
    from sdlc.state.atomic import read_state, write_state_atomic_sync
    from sdlc.state.model import State

    state = State(schema_version=1, next_monotonic_seq=7, epics={"e1": {"status": "active"}})
    write_state_atomic_sync(state, target)
    result = read_state(target)
    assert result == state


def test_missing_file_returns_none(target: Path) -> None:
    from sdlc.state.atomic import read_state

    assert not target.exists()
    assert read_state(target) is None


def test_malformed_json_raises_state_error(target: Path) -> None:
    from sdlc.errors import StateError
    from sdlc.state.atomic import read_state

    target.write_text("not valid json {{{", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        read_state(target)
    assert exc_info.value.details["reason"] == "json"


def test_schema_invalid_json_raises_state_error(target: Path) -> None:
    from sdlc.errors import StateError
    from sdlc.state.atomic import read_state

    # Valid JSON but invalid schema (extra forbidden field)
    target.write_text(json.dumps({"schema_version": 1, "unknown_field": True}), encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        read_state(target)
    assert exc_info.value.details["reason"] == "schema"


def test_multiple_writes_last_wins(target: Path) -> None:
    from sdlc.state.atomic import read_state, write_state_atomic_sync
    from sdlc.state.model import State

    for i in range(5):
        s = State(schema_version=1, next_monotonic_seq=i, epics={})
        write_state_atomic_sync(s, target)

    final = read_state(target)
    assert final is not None
    assert final.next_monotonic_seq == 4

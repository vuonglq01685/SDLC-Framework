"""Unit tests for sdlc.state.reader (AC7.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.errors import SchemaError, StateError
from sdlc.state.model import State
from sdlc.state.reader import CURRENT_SCHEMA_VERSION, read_state_or_refuse, read_state_raw

pytestmark = pytest.mark.unit

_VALID_V1 = {
    "schema_version": 1,
    "next_monotonic_seq": 0,
    "epics": {},
    "stories": {},
    "tasks": {},
    "phase": 1,
}


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_current_schema_version_is_1() -> None:
    assert CURRENT_SCHEMA_VERSION == 1


def test_read_state_or_refuse_returns_none_when_missing(tmp_path: Path) -> None:
    result = read_state_or_refuse(tmp_path / "nope.json")
    assert result is None


def test_read_state_or_refuse_passes_v1_state(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    _write_json(state_file, _VALID_V1)
    result = read_state_or_refuse(state_file)
    assert isinstance(result, State)
    assert result.schema_version == 1


def test_read_state_or_refuse_refuses_v2_with_exact_message(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    _write_json(state_file, {**_VALID_V1, "schema_version": 2})
    with pytest.raises(SchemaError) as exc_info:
        read_state_or_refuse(state_file)
    msg = exc_info.value.message
    assert "schema_version mismatch" in msg
    assert "sdlc migrate-v1" in msg


def test_read_state_or_refuse_refuses_v0_naming_convention(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    _write_json(state_file, {**_VALID_V1, "schema_version": 0})
    with pytest.raises(SchemaError):
        read_state_or_refuse(state_file)


def test_read_state_or_refuse_raises_state_error_on_missing_schema_version(
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "state.json"
    _write_json(state_file, {"foo": "bar"})
    with pytest.raises(StateError) as exc_info:
        read_state_or_refuse(state_file)
    assert exc_info.value.details.get("reason") == "missing_schema_version"


def test_read_state_or_refuse_raises_state_error_on_malformed_json(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("not-json", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        read_state_or_refuse(state_file)
    assert exc_info.value.details.get("reason") == "json"


def test_read_state_or_refuse_raises_state_error_on_non_object(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    _write_json(state_file, [1, 2, 3])
    with pytest.raises(StateError):
        read_state_or_refuse(state_file)


def test_read_state_raw_returns_dict_for_v2_state(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    payload = {"schema_version": 2, "foo": "bar"}
    _write_json(state_file, payload)
    result = read_state_raw(state_file)
    assert result == payload


def test_read_state_raw_returns_none_when_missing(tmp_path: Path) -> None:
    result = read_state_raw(tmp_path / "nope.json")
    assert result is None


def test_read_state_raw_raises_on_malformed_json(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("not-json", encoding="utf-8")
    with pytest.raises(StateError) as exc_info:
        read_state_raw(state_file)
    assert exc_info.value.details.get("reason") == "json"


# ---------------------------------------------------------------------------
# read_state_or_recover tests (Story 1.20 AC7.3)
# ---------------------------------------------------------------------------


def test_read_state_or_recover_returns_none_when_missing(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    result = read_state_or_recover(tmp_path / "nope.json", tmp_path / "journal.log")
    assert result is None


def test_read_state_or_recover_passes_v1_state(tmp_path: Path) -> None:
    import sys

    if sys.platform == "win32":
        pytest.skip("POSIX-only")

    from sdlc.state import write_state_atomic_sync
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    write_state_atomic_sync(State(), state_path)
    result = read_state_or_recover(state_path, tmp_path / "journal.log")
    assert isinstance(result, State)


def test_read_state_or_recover_wraps_schema_version_mismatch(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.log"
    _write_json(state_path, {"schema_version": 2, "next_monotonic_seq": 0, "epics": {}})

    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, journal_path)

    err = exc_info.value
    assert "state.json is malformed at " in err.message
    assert str(state_path) in err.message
    assert "sdlc rebuild-state" in err.message
    assert "sdlc migrate-vN" in err.message
    assert str(journal_path) in err.message
    assert "is untouched" in err.message
    assert err.details["reason"] == "schema_version_mismatch"
    assert "schema_version mismatch" in err.details["inner_message"]
    assert "sdlc migrate-v1" in err.details["inner_message"]
    assert err.__cause__ is not None


def test_read_state_or_recover_wraps_invalid_json(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.log"
    state_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, journal_path)

    err = exc_info.value
    assert "state.json is malformed at " in err.message
    assert "sdlc rebuild-state" in err.message
    assert err.details["reason"] == "json"


def test_read_state_or_recover_wraps_missing_schema_version(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    _write_json(state_path, {"foo": "bar"})

    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, tmp_path / "journal.log")

    assert "state.json is malformed at " in exc_info.value.message
    assert exc_info.value.details["reason"] == "missing_schema_version"


def test_read_state_or_recover_wraps_pydantic_validation_error(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    # extra="forbid" on State model — unknown field triggers pydantic ValidationError
    _write_json(
        state_path,
        {"schema_version": 1, "next_monotonic_seq": 0, "epics": {}, "unknown_field_xyz": "invalid"},
    )

    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, tmp_path / "journal.log")

    assert "state.json is malformed at " in exc_info.value.message
    assert exc_info.value.details["reason"] == "schema"


def test_read_state_or_recover_message_names_both_paths(tmp_path: Path) -> None:
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.log"
    state_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, journal_path)

    msg = exc_info.value.message
    assert str(state_path) in msg
    assert str(journal_path) in msg


def test_read_state_or_recover_does_not_read_journal(tmp_path: Path) -> None:
    """Journal is purely for message formatting — never read by read_state_or_recover."""
    from sdlc.state.reader import read_state_or_recover

    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.log"
    state_path.write_text("not-json", encoding="utf-8")
    # Write a malformed journal; if read_state_or_recover reads it, it would error differently
    journal_path.write_text("invalid-journal-content", encoding="utf-8")

    # Only the state.json error should surface (StateError with reason="json")
    with pytest.raises(StateError) as exc_info:
        read_state_or_recover(state_path, journal_path)

    assert exc_info.value.details["reason"] == "json"


# ---------------------------------------------------------------------------


def test_atomic_read_state_delegates_to_reader(tmp_path: Path) -> None:
    import sys

    if sys.platform == "win32":
        pytest.skip("POSIX-only")

    from sdlc.state.atomic import read_state, write_state_atomic_sync

    state_file = tmp_path / "state.json"
    write_state_atomic_sync(State(), state_file)

    result = read_state(state_file)
    assert isinstance(result, State)
    assert result.schema_version == 1

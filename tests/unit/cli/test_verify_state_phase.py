"""Defensive `_read_state_phase` coverage for `cli/verify` (Story 2A.10).

Pre-flight fallback:
  * Transient I/O failures (missing file / undecodable JSON) → ``phase=1``
    default so downstream pre-flight surfaces ``ERR_NOT_INITIALIZED`` or
    ``ERR_PHASE_MISMATCH`` instead of crashing on a missing key.
  * **Logical corruption** (P6 / DC4=(1) post-review 2026-05-12 Cluster C-J)
    — JSON decodes fine but the shape is wrong — raises
    :class:`sdlc.errors.StateError`; the orchestrator translates this into
    an ``ERR_STATE_CORRUPT`` envelope that suggests ``sdlc rebuild-state``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli.verify import _read_state_phase  # type: ignore[attr-defined]
from sdlc.errors import StateError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Transient failures — best-effort default per DC4
# ---------------------------------------------------------------------------


def test_read_state_phase_missing_file_returns_default(tmp_path: Path) -> None:
    """A non-existent `state.json` falls back to phase=1 (OSError → default)."""
    assert _read_state_phase(tmp_path / "nope.json") == 1


def test_read_state_phase_malformed_json_returns_default(tmp_path: Path) -> None:
    """Garbage in `state.json` falls back to phase=1 (JSONDecodeError → default)."""
    p = tmp_path / "state.json"
    p.write_text("not-json-at-all", encoding="utf-8")
    assert _read_state_phase(p) == 1


# ---------------------------------------------------------------------------
# Logical corruption — raise StateError per DC4=(1)
# ---------------------------------------------------------------------------


def test_read_state_phase_non_mapping_raises_state_error(tmp_path: Path) -> None:
    """A JSON list at top-level is logical corruption — raise StateError."""
    p = tmp_path / "state.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(StateError, match="must be a JSON object"):
        _read_state_phase(p)


def test_read_state_phase_phase_field_missing_raises_state_error(tmp_path: Path) -> None:
    """JSON object missing `phase` is logical corruption — raise StateError."""
    p = tmp_path / "state.json"
    p.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(StateError, match="missing required 'phase' field"):
        _read_state_phase(p)


def test_read_state_phase_phase_field_not_int_raises_state_error(tmp_path: Path) -> None:
    """`phase` present but not an int (string) — raise StateError."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": "one"}', encoding="utf-8")
    with pytest.raises(StateError, match="must be an integer"):
        _read_state_phase(p)


def test_read_state_phase_phase_field_bool_rejected(tmp_path: Path) -> None:
    """`bool` is a Python `int` subclass — explicitly rejected (P6 guard)."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": true}', encoding="utf-8")
    with pytest.raises(StateError, match="must be an integer"):
        _read_state_phase(p)


def test_read_state_phase_phase_out_of_range_below_raises(tmp_path: Path) -> None:
    """`phase: 0` is below the valid 1..6 range — raise StateError."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 0}', encoding="utf-8")
    with pytest.raises(StateError, match="out of range"):
        _read_state_phase(p)


def test_read_state_phase_phase_out_of_range_above_raises(tmp_path: Path) -> None:
    """`phase: 7` is above the valid 1..6 range — raise StateError."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 7}', encoding="utf-8")
    with pytest.raises(StateError, match="out of range"):
        _read_state_phase(p)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_read_state_phase_int_phase_returned_verbatim(tmp_path: Path) -> None:
    """`phase: 2` is returned as-is so callers can compare against `_REQUIRED_PHASE`."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 2}', encoding="utf-8")
    assert _read_state_phase(p) == 2


def test_read_state_phase_boundary_phase_one_accepted(tmp_path: Path) -> None:
    """`phase: 1` (lower boundary) returns 1."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 1}', encoding="utf-8")
    assert _read_state_phase(p) == 1


def test_read_state_phase_boundary_phase_six_accepted(tmp_path: Path) -> None:
    """`phase: 6` (upper boundary) returns 6."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 6}', encoding="utf-8")
    assert _read_state_phase(p) == 6

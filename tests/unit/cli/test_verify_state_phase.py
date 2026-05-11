"""Defensive `_read_state_phase` coverage for `cli/verify` (Story 2A.10).

Pre-flight fallback: any unreadable / malformed state.json yields the
default `phase=1` — the verify gate then defers to the ERR_NOT_INITIALIZED
checks instead of crashing on a missing key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli.verify import _read_state_phase  # type: ignore[attr-defined]

pytestmark = pytest.mark.unit


def test_read_state_phase_missing_file_returns_default(tmp_path: Path) -> None:
    """A non-existent `state.json` falls back to phase=1."""
    assert _read_state_phase(tmp_path / "nope.json") == 1


def test_read_state_phase_malformed_json_returns_default(tmp_path: Path) -> None:
    """Garbage in `state.json` falls back to phase=1."""
    p = tmp_path / "state.json"
    p.write_text("not-json-at-all", encoding="utf-8")
    assert _read_state_phase(p) == 1


def test_read_state_phase_non_mapping_returns_default(tmp_path: Path) -> None:
    """A JSON list at top-level falls back to phase=1."""
    p = tmp_path / "state.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert _read_state_phase(p) == 1


def test_read_state_phase_phase_field_not_int_returns_default(tmp_path: Path) -> None:
    """`phase` present but not an int falls back to phase=1."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": "one"}', encoding="utf-8")
    assert _read_state_phase(p) == 1


def test_read_state_phase_int_phase_returned_verbatim(tmp_path: Path) -> None:
    """`phase: 2` is returned as-is so callers can compare against `_REQUIRED_PHASE`."""
    p = tmp_path / "state.json"
    p.write_text('{"phase": 2}', encoding="utf-8")
    assert _read_state_phase(p) == 2

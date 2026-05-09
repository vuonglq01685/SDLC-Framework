"""Unit tests for write_state_raw_atomic_sync (AC7.3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_writes_valid_json(tmp_path: Path) -> None:
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"
    payload: dict[str, object] = {
        "schema_version": 2,
        "foo": "bar",
        "nested": {"key": "value"},
    }
    write_state_raw_atomic_sync(payload, state_file)

    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["foo"] == "bar"
    assert data["nested"] == {"key": "value"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_produces_canonical_json(tmp_path: Path) -> None:
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"
    payload: dict[str, object] = {"z_key": 1, "a_key": 2, "schema_version": 2}
    write_state_raw_atomic_sync(payload, state_file)

    raw = state_file.read_bytes()
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8").strip()
    parsed = json.loads(text)
    keys = list(parsed.keys())
    assert keys == sorted(keys), "keys must be sorted"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_roundtrips_v2_payload(tmp_path: Path) -> None:
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"
    payload: dict[str, object] = {
        "schema_version": 2,
        "epics": {},
        "stories": {},
        "tasks": {},
        "phase": 1,
        "next_monotonic_seq": 42,
    }
    write_state_raw_atomic_sync(payload, state_file)
    result = json.loads(state_file.read_text(encoding="utf-8"))
    assert result == payload


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_creates_tmp_then_renames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"
    write_state_raw_atomic_sync({"schema_version": 2}, state_file)

    tmp_file = tmp_path / "state.json.tmp"
    assert not tmp_file.exists(), "tmp file must be cleaned up (renamed)"
    assert state_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_raises_state_error_on_relative_path() -> None:
    from sdlc.errors import StateError
    from sdlc.state.atomic import write_state_raw_atomic_sync

    with pytest.raises(StateError) as exc_info:
        write_state_raw_atomic_sync({"schema_version": 2}, Path("relative/path.json"))
    assert exc_info.value.details.get("step") == "validate_path"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_raises_state_error_from_event_loop(
    tmp_path: Path,
) -> None:
    import asyncio

    from sdlc.errors import StateError
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"

    async def _call() -> None:
        write_state_raw_atomic_sync({"schema_version": 2}, state_file)

    with pytest.raises(StateError) as exc_info:
        asyncio.run(_call())
    assert exc_info.value.details.get("step") == "loop_check"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_nfc_normalizes_strings(tmp_path: Path) -> None:
    from sdlc.state.atomic import write_state_raw_atomic_sync

    state_file = tmp_path / "state.json"
    # Compose 'é' using NFD (e + combining accent) — should be NFC-normalized to single codepoint
    nfd_string = "é"
    nfc_string = "é"
    assert nfd_string != nfc_string

    write_state_raw_atomic_sync({"schema_version": 2, "label": nfd_string}, state_file)
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["label"] == nfc_string


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")
def test_write_state_raw_atomic_sync_not_in_canonical_write_api_name_sentinel() -> None:
    """Ensure _CANONICAL_WRITE_API sentinel includes the raw write function."""
    from sdlc.state.atomic import _CANONICAL_WRITE_API

    assert "sdlc.state.atomic.write_state_raw_atomic_sync" in _CANONICAL_WRITE_API

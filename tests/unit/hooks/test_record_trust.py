"""Unit tests for the hook-trust write surface.

Per Story 2A.5 DR1, the writer lives at ``sdlc.cli._hook_trust_writer`` —
``sdlc.hooks.tampering`` is pure logic. These tests cover the helper +
the canonical-payload builder that feeds it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sdlc.cli._hook_trust_writer import write_hook_hashes_atomic
from sdlc.errors import HookError
from sdlc.hooks._hash_store import _HookHashStore
from sdlc.hooks.tampering import build_hook_hash_store_payload

_VALID_HASH = "sha256:" + "a" * 64
_TS = "2026-05-10T12:00:00.000Z"
_HASHES: dict[str, str] = {"hook_a.py": _VALID_HASH}

_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only atomic write (DR1: Windows raises HookError)"
)


@pytest.mark.unit
class TestBuildHookHashStorePayload:
    """Pure-logic tests for the payload builder (no I/O)."""

    def test_payload_has_expected_keys(self) -> None:
        payload = build_hook_hash_store_payload(_HASHES, now_utc=_TS)
        assert payload == {
            "schema_version": 1,
            "trusted_at": _TS,
            "hooks_root": ".claude/hooks",
            "hashes": dict(_HASHES),
        }

    def test_payload_keys_sorted_by_relpath(self) -> None:
        unsorted = {"zzz.py": _VALID_HASH, "aaa.py": "sha256:" + "b" * 64}
        payload = build_hook_hash_store_payload(unsorted, now_utc=_TS)
        hashes = payload["hashes"]
        assert isinstance(hashes, dict)
        keys = list(hashes.keys())
        assert keys == sorted(keys)


@pytest.mark.unit
@_SKIP_WIN32
class TestWriteHookHashesAtomicPosix:
    def test_writes_to_correct_path(self, tmp_path: Path) -> None:
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        assert (tmp_path / "hook-hashes.json").exists()

    def test_written_file_round_trips_to_hook_hash_store(self, tmp_path: Path) -> None:
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = (tmp_path / "hook-hashes.json").read_text(encoding="utf-8")
        store = _HookHashStore.model_validate(json.loads(raw))
        assert store.trusted_at == _TS
        assert store.hashes == _HASHES

    def test_schema_version_is_1(self, tmp_path: Path) -> None:
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == 1

    def test_hooks_root_label_is_set(self, tmp_path: Path) -> None:
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["hooks_root"] == ".claude/hooks"

    def test_hashes_keys_sorted_in_output(self, tmp_path: Path) -> None:
        hashes = {"zzz.py": _VALID_HASH, "aaa.py": "sha256:" + "b" * 64}
        write_hook_hashes_atomic(tmp_path.resolve(), hashes, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        keys = list(raw["hashes"].keys())
        assert keys == sorted(keys)

    def test_second_write_overwrites_first(self, tmp_path: Path) -> None:
        ts1 = "2026-05-10T10:00:00.000Z"
        ts2 = "2026-05-10T11:00:00.000Z"
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=ts1)
        write_hook_hashes_atomic(tmp_path.resolve(), {}, now_utc=ts2)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["trusted_at"] == ts2
        assert raw["hashes"] == {}

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        content = (tmp_path / "hook-hashes.json").read_bytes()
        assert content.endswith(b"\n")

    def test_returns_resolved_target_path(self, tmp_path: Path) -> None:
        result = write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)
        assert result == (tmp_path / "hook-hashes.json").resolve()


@pytest.mark.unit
@_SKIP_WIN32
class TestWriteHookHashesAtomicityPosix:
    def test_io_failure_surfaces_as_hook_error(self, tmp_path: Path) -> None:
        with (
            patch(
                "sdlc.state.atomic.write_state_raw_atomic_sync",
                side_effect=OSError("simulated disk full"),
            ),
            pytest.raises(HookError, match="atomic write failed"),
        ):
            write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)


@pytest.mark.unit
@pytest.mark.skipif(
    sys.platform != "win32",
    reason="DR1: Windows raises HookError; runs only when actually on win32",
)
class TestWriteHookHashesAtomicWindowsRaises:
    def test_windows_raises_hook_error_with_dr1_marker(self, tmp_path: Path) -> None:
        with pytest.raises(HookError, match="DR1-Windows"):
            write_hook_hashes_atomic(tmp_path.resolve(), _HASHES, now_utc=_TS)

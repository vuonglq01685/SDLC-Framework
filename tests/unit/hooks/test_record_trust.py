"""Task 2.1 — unit tests for record_trust (TDD-first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sdlc.errors import HookError
from sdlc.hooks.tampering import _HookHashStore, record_trust

_VALID_HASH = "sha256:" + "a" * 64
_TS = "2026-05-10T12:00:00.000Z"
_HASHES: dict[str, str] = {"hook_a.py": _VALID_HASH}

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")


@pytest.mark.unit
@_SKIP_WIN32
class TestRecordTrustWrites:
    def test_writes_to_correct_path(self, tmp_path: Path) -> None:
        record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)
        assert (tmp_path / "hook-hashes.json").exists()

    def test_written_file_round_trips_to_hook_hash_store(self, tmp_path: Path) -> None:
        record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = (tmp_path / "hook-hashes.json").read_text(encoding="utf-8")
        store = _HookHashStore.model_validate(json.loads(raw))
        assert store.trusted_at == _TS
        assert store.hashes == _HASHES

    def test_schema_version_is_1(self, tmp_path: Path) -> None:
        record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == 1

    def test_hooks_root_label_is_set(self, tmp_path: Path) -> None:
        record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["hooks_root"] == ".claude/hooks"

    def test_hashes_keys_sorted_in_output(self, tmp_path: Path) -> None:
        hashes = {"zzz.py": _VALID_HASH, "aaa.py": "sha256:" + "b" * 64}
        record_trust(tmp_path.resolve(), hashes, now_utc=_TS)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        keys = list(raw["hashes"].keys())
        assert keys == sorted(keys)

    def test_second_write_overwrites_first(self, tmp_path: Path) -> None:
        ts1 = "2026-05-10T10:00:00.000Z"
        ts2 = "2026-05-10T11:00:00.000Z"
        record_trust(tmp_path.resolve(), _HASHES, now_utc=ts1)
        record_trust(tmp_path.resolve(), {}, now_utc=ts2)
        raw = json.loads((tmp_path / "hook-hashes.json").read_text(encoding="utf-8"))
        assert raw["trusted_at"] == ts2
        assert raw["hashes"] == {}

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)
        content = (tmp_path / "hook-hashes.json").read_bytes()
        assert content.endswith(b"\n")


@pytest.mark.unit
@_SKIP_WIN32
class TestRecordTrustAtomicity:
    def test_io_failure_surfaces_as_hook_error(self, tmp_path: Path) -> None:
        with (
            patch(
                "sdlc.state.atomic.write_state_raw_atomic_sync",
                side_effect=OSError("simulated disk full"),
            ),
            pytest.raises(HookError, match="record_trust write failed"),
        ):
            record_trust(tmp_path.resolve(), _HASHES, now_utc=_TS)

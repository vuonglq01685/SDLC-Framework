"""Task 3.1 — unit tests for detect_tampering + TamperReport (TDD-first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from sdlc.cli._hook_trust_writer import write_hook_hashes_atomic
from sdlc.hooks.tampering import detect_tampering

_VALID_HASH_A = "sha256:" + "a" * 64
_VALID_HASH_B = "sha256:" + "b" * 64
_VALID_HASH_C = "sha256:" + "c" * 64
_TS = "2026-05-10T12:00:00.000Z"

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only write test")


def _write_store(state_root: Path, hashes: dict[str, str], ts: str = _TS) -> None:
    write_hook_hashes_atomic(state_root.resolve(), hashes, now_utc=ts)


def _make_hooks(hooks_root: Path, files: dict[str, bytes]) -> None:
    for relpath, content in files.items():
        p = hooks_root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


@pytest.mark.unit
@_SKIP_WIN32
class TestDetectTamperingClean:
    def test_clean_when_hashes_match(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        hook_content = b"# hook a\n"
        (hooks / "a.py").write_bytes(hook_content)
        hashes: dict[str, str] = {}
        import hashlib

        hashes["a.py"] = f"sha256:{hashlib.sha256(hook_content).hexdigest()}"
        _write_store(state, hashes)
        report = detect_tampering(state, hooks)
        assert report.status == "clean"
        assert report.drift == ()

    def test_clean_report_has_empty_drift(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        _write_store(state, {})
        report = detect_tampering(state, hooks)
        assert report.status == "clean"
        assert len(report.drift) == 0


@pytest.mark.unit
@_SKIP_WIN32
class TestDetectTamperingTampered:
    def test_modified_file_produces_tampered_status(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        _write_store(state, {"mod.py": _VALID_HASH_A})
        (hooks / "mod.py").write_bytes(b"# different content\n")
        report = detect_tampering(state, hooks)
        assert report.status == "tampered"

    def test_added_file_detected(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        _write_store(state, {})
        (hooks / "new.py").write_bytes(b"# new\n")
        report = detect_tampering(state, hooks)
        assert report.status == "tampered"
        assert any(d.kind == "added" and d.relpath == "new.py" for d in report.drift)

    def test_removed_file_detected(self, tmp_path: Path) -> None:
        import hashlib

        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        content = b"# was here\n"
        h = f"sha256:{hashlib.sha256(content).hexdigest()}"
        _write_store(state, {"gone.py": h})
        # don't create the file — it's "removed"
        report = detect_tampering(state, hooks)
        assert report.status == "tampered"
        assert any(d.kind == "removed" and d.relpath == "gone.py" for d in report.drift)

    def test_drift_sorted_by_relpath(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        # Store 3 known hashes; add 3 new files that don't match
        _write_store(state, {"cc.py": _VALID_HASH_A, "aa.py": _VALID_HASH_B})
        (hooks / "aa.py").write_bytes(b"# changed\n")
        (hooks / "bb.py").write_bytes(b"# new\n")
        # cc.py is removed
        report = detect_tampering(state, hooks)
        assert report.status == "tampered"
        relpaths = [d.relpath for d in report.drift]
        assert relpaths == sorted(relpaths)

    def test_drift_tuple_len_equals_changed_files(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        _write_store(state, {"a.py": _VALID_HASH_A, "b.py": _VALID_HASH_B})
        (hooks / "a.py").write_bytes(b"# changed a\n")
        (hooks / "b.py").write_bytes(b"# changed b\n")
        report = detect_tampering(state, hooks)
        assert len(report.drift) == 2


@pytest.mark.unit
class TestDetectTamperingUninitialized:
    def test_uninitialized_when_no_store(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        report = detect_tampering(state, hooks)
        assert report.status == "uninitialized"

    def test_uninitialized_has_empty_expected(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        report = detect_tampering(state, hooks)
        assert report.expected == {}


@pytest.mark.unit
class TestDetectTamperingCorrupted:
    def test_corrupted_when_bad_json(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        (state / "hook-hashes.json").write_text("not-json{{{", encoding="utf-8")
        report = detect_tampering(state, hooks)
        assert report.status == "corrupted"

    def test_corrupted_when_schema_mismatch(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        bad = {"schema_version": 99, "trusted_at": "x", "hooks_root": "y", "hashes": {}}
        (state / "hook-hashes.json").write_text(json.dumps(bad), encoding="utf-8")
        report = detect_tampering(state, hooks)
        assert report.status == "corrupted"

    def test_corrupted_has_empty_expected(self, tmp_path: Path) -> None:
        hooks = tmp_path / "hooks"
        state = tmp_path / "state"
        state.mkdir()
        hooks.mkdir()
        (state / "hook-hashes.json").write_text("bad", encoding="utf-8")
        report = detect_tampering(state, hooks)
        assert report.expected == {}

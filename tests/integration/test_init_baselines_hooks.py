"""Task 6.1 — integration tests: sdlc init baselines hook hashes (AC7)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _clihelper import sdlc_uv_argv

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
_UV_RUN = sdlc_uv_argv()


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_UV_RUN + args, capture_output=True, text=True, cwd=cwd)


@pytest.mark.integration
@_SKIP_WIN32
class TestInitBaselinesHooks:
    def test_init_creates_hook_hashes_json(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        store = tmp_path / ".claude" / "state" / "hook-hashes.json"
        assert store.exists(), "sdlc init must create hook-hashes.json"

    def test_hook_hashes_json_parses_correctly(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        store = tmp_path / ".claude" / "state" / "hook-hashes.json"
        data = json.loads(store.read_text())
        assert data["schema_version"] == 1
        assert "trusted_at" in data
        assert "hashes" in data
        assert isinstance(data["hashes"], dict)

    def test_init_journal_contains_hooks_trusted_entry(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        journal = tmp_path / ".claude" / "state" / "journal.log"
        entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        kinds = [e["kind"] for e in entries]
        assert "hooks_trusted" in kinds, f"Expected hooks_trusted in journal; got kinds: {kinds}"

    def test_init_journal_hooks_trusted_has_via_init(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        journal = tmp_path / ".claude" / "state" / "journal.log"
        entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
        trusted = [e for e in entries if e["kind"] == "hooks_trusted"]
        assert any(e.get("payload", {}).get("via") == "sdlc init" for e in trusted), (
            "Expected hooks_trusted entry with via='sdlc init'"
        )

    def test_init_state_seq_advanced_after_hooks_trusted(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        state = json.loads((tmp_path / ".claude" / "state" / "state.json").read_text())
        # seq must be >= 1 since hooks_trusted was appended at seq=0
        assert state["next_monotonic_seq"] >= 1

    def test_scan_still_works_after_init_with_baseline(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["scan"], cwd=tmp_path)
        assert result.returncode == 0

    def test_scan_after_init_shows_clean_trust_state_in_json(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "scan"], cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        trust_state = data.get("trust_state", {})
        assert trust_state.get("status") == "clean"


@pytest.mark.integration
@_SKIP_WIN32
class TestInitFailLoudFixtureCheck:
    """P17: every test must assert init returncode==0 before relying on its output."""

    def test_init_returncode_is_zero_in_clean_workspace(self, tmp_path: Path) -> None:
        result = _run(["init"], cwd=tmp_path)
        assert result.returncode == 0, (
            f"sdlc init must succeed cleanly in empty tmp_path; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


@pytest.mark.integration
@_SKIP_WIN32
class TestInitHashContentBehavior:
    """P10: assert that recorded hashes match real files, not just shape."""

    def test_recorded_hashes_match_actual_hook_file_contents(self, tmp_path: Path) -> None:
        import hashlib

        result = _run(["init"], cwd=tmp_path)
        assert result.returncode == 0
        store = tmp_path / ".claude" / "state" / "hook-hashes.json"
        data = json.loads(store.read_text())
        hooks_root = tmp_path / ".claude" / "hooks"
        # For every hook file under .claude/hooks/, verify the recorded hash
        # matches the actual sha256 of the file's bytes-on-disk.
        for relpath, recorded_hash in data["hashes"].items():
            actual_file = hooks_root / relpath
            assert actual_file.exists(), f"hash entry for {relpath} but file is missing"
            actual_hash = "sha256:" + hashlib.sha256(actual_file.read_bytes()).hexdigest()
            assert recorded_hash == actual_hash, (
                f"recorded hash for {relpath} does not match file contents: "
                f"recorded={recorded_hash} actual={actual_hash}"
            )

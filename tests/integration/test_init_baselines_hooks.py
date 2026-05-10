"""Task 6.1 — integration tests: sdlc init baselines hook hashes (AC7)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
_UV_RUN = ["uv", "run", "sdlc"]


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

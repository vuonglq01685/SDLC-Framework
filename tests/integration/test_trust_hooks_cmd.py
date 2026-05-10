"""Task 5.1 — integration tests for sdlc trust-hooks CLI command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SKIP_WIN32 = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only hooks/atomic")
_UV_RUN = ["uv", "run", "sdlc"]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _UV_RUN + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


@pytest.mark.integration
@_SKIP_WIN32
class TestTrustHooksCmdNotInitialized:
    def test_exits_nonzero_when_not_sdlc_workspace(self, tmp_path: Path) -> None:
        result = _run(["trust-hooks"], cwd=tmp_path)
        assert result.returncode != 0

    def test_error_message_to_stderr(self, tmp_path: Path) -> None:
        result = _run(["trust-hooks"], cwd=tmp_path)
        assert "sdlc init" in result.stderr or "not an sdlc workspace" in result.stderr


@pytest.mark.integration
@_SKIP_WIN32
class TestTrustHooksCmdHappyPath:
    def test_happy_path_exits_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["trust-hooks"], cwd=tmp_path)
        assert result.returncode == 0

    def test_happy_path_emits_ok_to_stdout(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["trust-hooks"], cwd=tmp_path)
        assert "[OK] hook hashes recorded:" in result.stdout

    def test_happy_path_writes_hash_store(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        store_path = tmp_path / ".claude" / "state" / "hook-hashes.json"
        assert store_path.exists()

    def test_happy_path_hash_store_is_valid_json(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        store_path = tmp_path / ".claude" / "state" / "hook-hashes.json"
        data = json.loads(store_path.read_text())
        assert data["schema_version"] == 1
        assert "trusted_at" in data
        assert "hashes" in data

    def test_retrust_overwrites_previous_store(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        store_after = json.loads((tmp_path / ".claude" / "state" / "hook-hashes.json").read_text())
        # trusted_at may differ if clock moved; schema must still be 1
        assert store_after["schema_version"] == 1
        assert isinstance(store_after["hashes"], dict)

    def test_journal_gains_hooks_trusted_entry(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        journal_path = tmp_path / ".claude" / "state" / "journal.log"
        entries = [
            json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()
        ]
        kinds = [e["kind"] for e in entries]
        assert "hooks_trusted" in kinds

    def test_hooks_trusted_journal_entry_has_files_payload(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        _run(["trust-hooks"], cwd=tmp_path)
        journal_path = tmp_path / ".claude" / "state" / "journal.log"
        entries = [
            json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()
        ]
        trusted_entries = [e for e in entries if e["kind"] == "hooks_trusted"]
        assert len(trusted_entries) >= 1
        last = trusted_entries[-1]
        assert "files" in last["payload"]
        assert isinstance(last["payload"]["files"], list)


@pytest.mark.integration
@_SKIP_WIN32
class TestTrustHooksCmdJsonOutput:
    def test_json_flag_exits_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "trust-hooks"], cwd=tmp_path)
        assert result.returncode == 0

    def test_json_envelope_shape(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "trust-hooks"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data.get("command") == "trust-hooks"
        assert "file_count" in data
        assert "trusted_at" in data

    def test_json_file_count_is_integer(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "trust-hooks"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert isinstance(data["file_count"], int)

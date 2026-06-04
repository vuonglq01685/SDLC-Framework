"""Task 7.1 — integration tests: sdlc scan warns on hook tampering (AC5, AC7)."""

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
class TestScanClean:
    def test_clean_scan_exits_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["scan"], cwd=tmp_path)
        assert result.returncode == 0

    def test_clean_scan_no_warn_to_stderr(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["scan"], cwd=tmp_path)
        assert "[WARN]" not in result.stderr

    def test_clean_scan_json_trust_state_clean(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "scan"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["trust_state"]["status"] == "clean"

    def test_clean_scan_json_drift_count_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        result = _run(["--json", "scan"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["trust_state"]["drift_count"] == 0


@pytest.mark.integration
@_SKIP_WIN32
class TestScanUninitialized:
    def test_uninitialized_scan_exits_zero(self, tmp_path: Path) -> None:
        # init without baseline: remove hook-hashes.json if exists
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "state" / "hook-hashes.json").unlink(missing_ok=True)
        result = _run(["scan"], cwd=tmp_path)
        assert result.returncode == 0

    def test_uninitialized_scan_warns_to_stderr(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "state" / "hook-hashes.json").unlink(missing_ok=True)
        result = _run(["scan"], cwd=tmp_path)
        assert "[WARN]" in result.stderr

    def test_uninitialized_scan_json_trust_state_status(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "state" / "hook-hashes.json").unlink(missing_ok=True)
        result = _run(["--json", "scan"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["trust_state"]["status"] == "uninitialized"


@pytest.mark.integration
@_SKIP_WIN32
class TestScanTampered:
    def test_tampered_scan_exits_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        # Add a new hook file (adds drift)
        hook = tmp_path / ".claude" / "hooks" / "injected.py"
        hook.write_text("# injected\n")
        result = _run(["scan"], cwd=tmp_path)
        assert result.returncode == 0

    def test_tampered_scan_warns_to_stderr(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "hooks" / "injected.py").write_text("# injected\n")
        result = _run(["scan"], cwd=tmp_path)
        assert "[WARN]" in result.stderr

    def test_tampered_scan_json_trust_state_tampered(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "hooks" / "injected.py").write_text("# injected\n")
        result = _run(["--json", "scan"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["trust_state"]["status"] == "tampered"

    def test_tampered_scan_json_drift_count_nonzero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "hooks" / "injected.py").write_text("# injected\n")
        result = _run(["--json", "scan"], cwd=tmp_path)
        data = json.loads(result.stdout)
        assert data["trust_state"]["drift_count"] > 0


@pytest.mark.integration
@_SKIP_WIN32
class TestScanCorrupted:
    def test_corrupted_scan_exits_zero(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "state" / "hook-hashes.json").write_text("bad json")
        result = _run(["scan"], cwd=tmp_path)
        assert result.returncode == 0

    def test_corrupted_scan_warns_to_stderr(self, tmp_path: Path) -> None:
        _run(["init"], cwd=tmp_path)
        (tmp_path / ".claude" / "state" / "hook-hashes.json").write_text("bad json")
        result = _run(["scan"], cwd=tmp_path)
        assert "[WARN]" in result.stderr

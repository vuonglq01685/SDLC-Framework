"""End-to-end walking skeleton: sdlc init → sdlc scan → sdlc status (Story 1.17 AC7)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH — skipping subprocess e2e test",
)
_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32",
    reason="journal.append_sync is POSIX-only; scan e2e skipped on Windows",
)


def _run(args: list[str], cwd: Path, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # type: ignore[call-overload]
        ["uv", "run", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


@_SKIP_NO_UV
def test_sdlc_init_then_status_exit_zero(tmp_path: Path) -> None:
    """sdlc init followed by sdlc status must both succeed."""
    r1 = _run(["sdlc", "init"], tmp_path)
    assert r1.returncode == 0, f"init failed: {r1.stderr}"
    r2 = _run(["sdlc", "status"], tmp_path)
    assert r2.returncode == 0, f"status failed: {r2.stderr}"


@_SKIP_NO_UV
def test_sdlc_status_after_init_shows_phase_requirement(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    r = _run(["sdlc", "status"], tmp_path)
    assert "Phase: 1 (Requirement)" in r.stdout


@_SKIP_NO_UV
def test_sdlc_status_json_after_init(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    r = _run(["sdlc", "--json", "status"], tmp_path)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["command"] == "status"
    assert payload["phase"] == 1
    assert payload["phase_name"] == "Requirement"
    # Story 2A.5: init now appends hooks_trusted journal entry, so last_updated_ts is set.
    assert payload["last_updated_ts"] is not None
    assert payload["last_updated_ts"].endswith("Z")


@_SKIP_NO_UV
@_SKIP_WIN32
def test_sdlc_scan_after_init_exit_zero(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    r = _run(["sdlc", "scan"], tmp_path)
    assert r.returncode == 0, f"scan failed:\nstdout={r.stdout}\nstderr={r.stderr}"


@_SKIP_NO_UV
@_SKIP_WIN32
def test_sdlc_init_scan_status_full_skeleton(tmp_path: Path) -> None:
    """Full walking skeleton: init → scan → status must all succeed."""
    for cmd in [["sdlc", "init"], ["sdlc", "scan"], ["sdlc", "status"]]:
        r = _run(cmd, tmp_path)
        assert r.returncode == 0, f"{cmd} failed:\nstdout={r.stdout}\nstderr={r.stderr}"


@_SKIP_NO_UV
@_SKIP_WIN32
def test_sdlc_scan_json_emits_canonical_envelope(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    r = _run(["sdlc", "--json", "scan"], tmp_path)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["command"] == "scan"
    assert payload["epic_count"] == 0
    assert payload["story_count"] == 0
    assert payload["task_count"] == 0


@_SKIP_NO_UV
@_SKIP_WIN32
def test_sdlc_status_last_updated_ts_after_scan(tmp_path: Path) -> None:
    _run(["sdlc", "init"], tmp_path)
    _run(["sdlc", "scan"], tmp_path)
    r = _run(["sdlc", "--json", "status"], tmp_path)
    payload = json.loads(r.stdout)
    assert payload["last_updated_ts"] is not None, (
        "last_updated_ts should be set after scan writes a journal entry"
    )


@_SKIP_NO_UV
def test_sdlc_status_refuses_before_init(tmp_path: Path) -> None:
    r = _run(["sdlc", "status"], tmp_path)
    assert r.returncode == 1, f"Expected exit 1 before init; got {r.returncode}"

"""End-to-end integration tests for sdlc trace, replay, logs (Story 1.18, AC7.7)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def _uv_sdlc(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "sdlc", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _append_journal_entry(journal_path: Path, seq: int, task_id: str) -> None:
    from sdlc.contracts.journal_entry import JournalEntry

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=f"2026-01-01T00:00:{seq:02d}Z",
        actor="cli",
        kind="scan_completed",
        target_id=task_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload={},
    )
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
@pytest.mark.skipif(sys.platform == "win32", reason="subprocess-based tests skip on Windows")
def test_full_lifecycle_init_scan_trace_replay_logs(tmp_path: Path) -> None:
    """Full lifecycle: init → manually add journal entry → trace/replay/logs all exit 0."""
    import subprocess as _sp

    git = _sp.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    assert git.returncode == 0

    r = _uv_sdlc("init", cwd=tmp_path)
    assert r.returncode == 0, f"sdlc init failed: {r.stderr}"

    r = _uv_sdlc("scan", cwd=tmp_path)
    assert r.returncode == 0, f"sdlc scan failed: {r.stderr}"

    task_id = "EPIC-foo-S01-bar-T01-baz"
    journal = tmp_path / ".claude" / "state" / "journal.log"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    # sdlc trace
    r = _uv_sdlc("trace", task_id, cwd=tmp_path)
    assert r.returncode == 0, f"sdlc trace failed: {r.stderr}"
    assert task_id in r.stdout

    # sdlc replay 1
    r = _uv_sdlc("replay", "1", cwd=tmp_path)
    assert r.returncode == 0, f"sdlc replay failed: {r.stderr}"
    assert "--- line 1 ---" in r.stdout

    # sdlc logs
    r = _uv_sdlc("logs", cwd=tmp_path)
    assert r.returncode == 0, f"sdlc logs failed: {r.stderr}"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
@pytest.mark.skipif(sys.platform == "win32", reason="subprocess-based tests skip on Windows")
@pytest.mark.parametrize(
    "command_args",
    [
        ("trace", "EPIC-foo-S01-bar-T01-baz"),
        ("replay", "1"),
        ("logs",),
    ],
)
def test_no_color_flag_strips_ansi_on_trace_replay_logs(
    tmp_path: Path, command_args: tuple[str, ...]
) -> None:
    """--no-color removes all ANSI escapes from stdout and stderr."""
    import subprocess as _sp

    _sp.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    r = _uv_sdlc("init", cwd=tmp_path)
    assert r.returncode == 0
    r = _uv_sdlc("scan", cwd=tmp_path)
    assert r.returncode == 0

    task_id = "EPIC-foo-S01-bar-T01-baz"
    journal = tmp_path / ".claude" / "state" / "journal.log"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    r = subprocess.run(
        ["uv", "run", "sdlc", "--no-color", *command_args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r.returncode == 0, f"command failed: {r.stderr}"
    assert "\x1b[" not in r.stdout, "ANSI found in stdout"
    assert "\x1b[" not in r.stderr, "ANSI found in stderr"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
@pytest.mark.skipif(sys.platform == "win32", reason="subprocess-based tests skip on Windows")
@pytest.mark.parametrize(
    "command_args,expected_key",
    [
        (("trace", "EPIC-foo-S01-bar-T01-baz"), "task_id"),
        (("replay", "1"), "lines"),
        (("logs",), "filters"),
    ],
)
def test_json_mode_emits_canonical_envelope_for_trace_replay_logs(
    tmp_path: Path,
    command_args: tuple[str, ...],
    expected_key: str,
) -> None:
    """--json emits a parseable JSON envelope with the expected key."""
    import subprocess as _sp

    _sp.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    r = _uv_sdlc("init", cwd=tmp_path)
    assert r.returncode == 0
    r = _uv_sdlc("scan", cwd=tmp_path)
    assert r.returncode == 0

    task_id = "EPIC-foo-S01-bar-T01-baz"
    journal = tmp_path / ".claude" / "state" / "journal.log"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    r = subprocess.run(
        ["uv", "run", "sdlc", "--json", *command_args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r.returncode == 0, f"--json command failed: {r.stderr}"
    payload: dict[str, Any] = json.loads(r.stdout)
    assert "command" in payload
    assert expected_key in payload

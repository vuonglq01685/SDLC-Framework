"""Integration test for sdlc logs --follow via subprocess (Story 1.18, AC7.8)."""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="follow-mode subprocess flaky on Windows"),
]


def _append_journal_entry(journal_path: Path, seq: int) -> None:
    from sdlc.contracts.journal_entry import JournalEntry

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=f"2026-06-01T00:00:{seq:02d}Z",
        actor="cli",
        kind="scan_completed",
        target_id="state",
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload={},
    )
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
def test_logs_follow_picks_up_new_entry(tmp_path: Path) -> None:
    """sdlc logs --follow picks up entries appended after it starts."""
    git = subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    assert git.returncode == 0

    init = subprocess.run(
        ["uv", "run", "sdlc", "init"], cwd=tmp_path, capture_output=True, check=False
    )
    assert init.returncode == 0, f"sdlc init failed: {init.stderr}"

    scan = subprocess.run(
        ["uv", "run", "sdlc", "scan"], cwd=tmp_path, capture_output=True, check=False
    )
    assert scan.returncode == 0, f"sdlc scan failed: {scan.stderr}"

    journal = tmp_path / ".claude" / "state" / "journal.log"

    child = subprocess.Popen(
        ["uv", "run", "sdlc", "--no-color", "logs", "--follow"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.5)
        _append_journal_entry(journal, seq=1)
        time.sleep(0.6)
        child.send_signal(signal.SIGINT)
        stdout, _ = child.communicate(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()

    assert "scan_completed" in stdout, f"follow did not emit the new entry. stdout={stdout!r}"

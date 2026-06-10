"""Integration test for sdlc logs --follow via subprocess (Story 1.18, AC7.8)."""

from __future__ import annotations

import contextlib
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

import pytest

from _clihelper import sdlc_uv_argv

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="follow-mode subprocess flaky on Windows"),
]

# Generous deadline that absorbs `uv run` cold-start on slow shared runners (py3.10 macOS
# measured the original fixed `sleep(0.5)` racing the process startup → empty stdout). We
# poll on observed output instead of guessing a sleep, so a slow start costs latency, not a
# flake.
_STARTUP_TIMEOUT_S = 20.0
# follow-mode polls the journal every 0.25s (logs._FOLLOW_INTERVAL_S); 10s is ample headroom.
_PICKUP_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05
# Synthetic ts of the entry appended *after* follow starts — distinct from every historical
# entry's real wall-clock ts, so matching it proves follow picked up the NEW entry (not just
# the historical replay).
_APPENDED_TS = "2026-06-01T00:00:01Z"


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


def _spawn_drainer(stream: IO[str], sink: list[str], lock: threading.Lock) -> threading.Thread:
    """Continuously drain a subprocess pipe into ``sink`` until EOF.

    Uses ``readline`` (not ``for line in stream``) to avoid Python's iterator read-ahead,
    which would withhold lines from a live pipe until a full block accumulates.
    """

    def _drain() -> None:
        for line in iter(stream.readline, ""):
            with lock:
                sink.append(line)

    thread = threading.Thread(target=_drain, daemon=True)
    thread.start()
    return thread


def _wait_until(predicate: Callable[[], bool], timeout: float) -> bool:
    """Poll ``predicate`` until true or ``timeout`` elapses (monotonic clock)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(_POLL_INTERVAL_S)
    return predicate()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
def test_logs_follow_picks_up_new_entry(tmp_path: Path) -> None:
    """sdlc logs --follow picks up entries appended after it starts."""
    git = subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    assert git.returncode == 0

    init = subprocess.run(sdlc_uv_argv("init"), cwd=tmp_path, capture_output=True, check=False)
    assert init.returncode == 0, f"sdlc init failed: {init.stderr}"

    scan = subprocess.run(sdlc_uv_argv("scan"), cwd=tmp_path, capture_output=True, check=False)
    assert scan.returncode == 0, f"sdlc scan failed: {scan.stderr}"

    journal = tmp_path / ".claude" / "state" / "journal.log"

    # --json emits line-flushed NDJSON (typer.echo flushes per line), so the reader thread
    # sees the historical replay + each followed entry as soon as it is written.
    child = subprocess.Popen(
        sdlc_uv_argv("--json", "logs", "--follow"),
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert child.stdout is not None and child.stderr is not None  # stdout/stderr=PIPE
    out_lines: list[str] = []
    err_lines: list[str] = []
    lock = threading.Lock()
    out_reader = _spawn_drainer(child.stdout, out_lines, lock)
    err_reader = _spawn_drainer(child.stderr, err_lines, lock)

    def _stdout() -> str:
        with lock:
            return "".join(out_lines)

    def _stderr() -> str:
        with lock:
            return "".join(err_lines)

    started = False
    picked_up = False
    try:
        # Readiness: the historical pass emits the existing scan_completed entry. Wait for
        # it (deadline, not fixed sleep) so a slow `uv run` cold-start cannot race us.
        started = _wait_until(lambda: "scan_completed" in _stdout(), _STARTUP_TIMEOUT_S)
        assert started, (
            "follow never emitted the historical entry within "
            f"{_STARTUP_TIMEOUT_S}s (cold-start?). stderr={_stderr()!r}"
        )
        # Now follow is live — append a NEW entry and confirm follow tails it.
        _append_journal_entry(journal, seq=1)
        picked_up = _wait_until(lambda: _APPENDED_TS in _stdout(), _PICKUP_TIMEOUT_S)
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=10)
        if child.poll() is None:
            child.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=5)
        out_reader.join(timeout=5)
        err_reader.join(timeout=5)
        # Close the pipes once the drainers have hit EOF — filterwarnings=error promotes a
        # leaked-fd ResourceWarning to a test failure.
        for stream in (child.stdout, child.stderr):
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()

    stdout = _stdout()
    assert "scan_completed" in stdout, (
        f"follow did not emit the historical entry. stdout={stdout!r} stderr={_stderr()!r}"
    )
    assert picked_up, (
        f"follow did not pick up the entry appended after start (ts={_APPENDED_TS}). "
        f"stdout={stdout!r} stderr={_stderr()!r}"
    )

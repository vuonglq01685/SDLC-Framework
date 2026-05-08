from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("POSIX flock(2) only — see Architecture §573", allow_module_level=True)

from sdlc.concurrency.locks import file_lock

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX flock(2) only — see Architecture §573",
)

# Child script: acquires the lock, prints ACQUIRED, then sleeps indefinitely.
_HOLDER_SCRIPT_TMPL = (
    "import sys, time; "
    "sys.path.insert(0, {src_path!r}); "
    "from sdlc.concurrency.locks import file_lock; "
    "lk = file_lock({lock_file!r}); "
    "lk.__enter__(); "
    "print('ACQUIRED', flush=True); "
    "time.sleep(30)"
)


@pytest.mark.integration
def test_lock_released_on_holder_kill(tmp_path: Path) -> None:
    """POSIX flock(2): kernel releases orphaned lock when process is killed."""
    lock_file = str(tmp_path / "scratch.lock")
    src_path = str(Path(__file__).resolve().parents[3] / "src")

    script = _HOLDER_SCRIPT_TMPL.format(src_path=src_path, lock_file=lock_file)
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None

    line = proc.stdout.readline()
    assert line.strip() == b"ACQUIRED", f"Unexpected child output: {line!r}"

    # Kill the holder mid-lock
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()

    # Parent must acquire within 2s — kernel auto-releases orphaned fds
    t1 = time.monotonic()
    with file_lock(lock_file):
        pass
    elapsed = time.monotonic() - t1

    assert elapsed <= 2.0, f"Lock recovery took {elapsed:.2f}s; expected ≤2s"

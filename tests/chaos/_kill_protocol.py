"""Child-process protocol runner with kill instrumentation for chaos tests (Story 1.10).

This module is the entrypoint spawned by multiprocessing.Process. It instruments
sdlc.state.atomic._write_protocol_body via monkey-patching to pause at the declared
kill point; the parent then issues SIGKILL.

The instrumentation shares the production protocol body — it uses unittest.mock.patch
with a side-effect wrapper, NOT a duplicated implementation.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch

if sys.platform == "win32":
    raise ImportError("_kill_protocol is POSIX-only — fcntl + signal semantics required")


def _pause_at(kill_point_name: str) -> None:
    """Send SIGSTOP to self so parent can SIGKILL us."""
    os.kill(os.getpid(), signal.SIGSTOP)


_KP_DISPATCH: dict[str, str] = {
    "AFTER_TMP_OPEN": "after_tmp_open",
    "MID_TMP_WRITE": "mid_tmp_write",
    "AFTER_TMP_WRITE": "after_tmp_write",
    "AFTER_TMP_FSYNC": "after_tmp_fsync",
    "AFTER_FLOCK_ACQUIRE": "after_flock_acquire",
    "AFTER_RENAME": "after_rename",
    "AFTER_PARENT_DIR_FSYNC": "after_parent_dir_fsync",
    # KP8: Lock release races kill — same instrumentation as KP7 (body done, lock still held)
    "BEFORE_FLOCK_RELEASE": "after_parent_dir_fsync",
    # KP9: OS-crash is post-rename eviction; same process-kill point as KP6
    "OS_CRASH_PRE_FSYNC": "after_rename",
    "RECOVERY_OF_RECOVERY": "recovery_of_recovery",
}


def _run_protocol_until_kill_point(
    kill_point_name: str,
    seed: int,
    target_path_str: str,
) -> None:
    """Child-process entrypoint. Runs the atomic write protocol up to the specified kill point.

    Called by multiprocessing.Process in test_atomic_write_kill_points.py.
    The parent issues SIGKILL after the child sends SIGSTOP at the kill point.
    """
    from sdlc.state.model import State

    target = Path(target_path_str)
    state = State(schema_version=1, next_monotonic_seq=seed % (2**31), epics={})

    _dispatch_kill_point(kill_point_name, seed, state, target)


def _dispatch_kill_point(kill_point_name: str, seed: int, state: object, target: Path) -> None:
    """Dispatch to the appropriate kill-point instrumentation helper."""
    # Populate after helpers are defined (see _KP_HANDLER_MAP at module bottom)
    handler_name = _KP_DISPATCH.get(kill_point_name)
    if handler_name is None:
        raise ValueError(f"Unknown kill point: {kill_point_name}")
    fn = _KP_HANDLER_MAP[handler_name]
    if handler_name == "mid_tmp_write":
        fn(state, target, seed)
    else:
        fn(state, target)


# ---------------------------------------------------------------------------
# Kill point instrumentation helpers
# ---------------------------------------------------------------------------


def _install_kp_after_tmp_open(state: object, target: Path) -> None:
    """KP1: pause after opening tmp file (before writing content)."""
    import sdlc.state.atomic as _atomic

    original_open = os.open

    call_count = [0]

    def patched_open(path: str, flags: int, mode: int = 0o777) -> int:
        fd = original_open(path, flags, mode)
        if path == str(target.with_suffix(target.suffix + ".tmp")):
            call_count[0] += 1
            if call_count[0] == 1:
                _pause_at("AFTER_TMP_OPEN")
        return fd

    with patch.object(_atomic.os, "open", side_effect=patched_open):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_mid_tmp_write(state: object, target: Path, seed: int) -> None:
    """KP2: pause after writing first half of canonical bytes."""
    import sdlc.state.atomic as _atomic
    from sdlc.state.atomic import _canonicalize_state

    canonical = _canonicalize_state(state)  # type: ignore[arg-type]
    cut = max(1, len(canonical) // 2)
    write_count = [0]
    original_write = os.write

    def patched_write(fd: int, data: bytes) -> int:
        write_count[0] += 1
        if write_count[0] == 1:
            # Write only first half
            n = original_write(fd, data[:cut])
            _pause_at("MID_TMP_WRITE")
            return n
        return original_write(fd, data)

    with patch.object(_atomic.os, "write", side_effect=patched_write):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_after_tmp_write(state: object, target: Path) -> None:
    """KP3: pause after writing full content but before fsync."""
    import sdlc.state.atomic as _atomic

    write_count = [0]
    original_write = os.write

    def patched_write(fd: int, data: bytes) -> int:
        n = original_write(fd, data)
        write_count[0] += 1
        if write_count[0] == 1:
            _pause_at("AFTER_TMP_WRITE")
        return n

    with patch.object(_atomic.os, "write", side_effect=patched_write):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_after_tmp_fsync(state: object, target: Path) -> None:
    """KP4: pause after fsyncing tmp, before flock acquire."""
    import sdlc.state.atomic as _atomic

    fsync_count = [0]
    original_fsync = os.fsync

    def patched_fsync(fd: int) -> None:
        original_fsync(fd)
        fsync_count[0] += 1
        if fsync_count[0] == 1:  # first fsync = tmp fd
            _pause_at("AFTER_TMP_FSYNC")

    with patch.object(_atomic.os, "fsync", side_effect=patched_fsync):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_after_flock_acquire(state: object, target: Path) -> None:
    """KP5: pause after flock acquire, before rename."""
    import sdlc.state.atomic as _atomic

    original_body = _atomic._write_protocol_body

    def patched_body(s: object, t: object, sync_mode: bool = False) -> None:
        _pause_at("AFTER_FLOCK_ACQUIRE")
        original_body(s, t, sync_mode)  # type: ignore[arg-type]

    with patch.object(_atomic, "_write_protocol_body", side_effect=patched_body):
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_after_rename(state: object, target: Path) -> None:
    """KP6: pause after rename, before parent dir fsync."""
    import sdlc.state.atomic as _atomic

    replace_count = [0]
    original_replace = os.replace

    def patched_replace(src: str, dst: str) -> None:
        original_replace(src, dst)
        replace_count[0] += 1
        if replace_count[0] == 1:
            _pause_at("AFTER_RENAME")

    with patch.object(_atomic.os, "replace", side_effect=patched_replace):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


def _install_kp_after_parent_dir_fsync(state: object, target: Path) -> None:
    """KP7/KP8: pause after parent dir fsync, before lock release."""
    import sdlc.state.atomic as _atomic

    fsync_count = [0]
    original_fsync = os.fsync

    def patched_fsync(fd: int) -> None:
        original_fsync(fd)
        fsync_count[0] += 1
        if fsync_count[0] == 2:  # second fsync = parent dir fd
            _pause_at("AFTER_PARENT_DIR_FSYNC")

    with patch.object(_atomic.os, "fsync", side_effect=patched_fsync):  # type: ignore[attr-defined]
        try:
            from sdlc.state.atomic import write_state_atomic_sync

            write_state_atomic_sync(state, target)  # type: ignore[arg-type]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Dispatch table — must be defined AFTER all _install_kp_* helpers
# ---------------------------------------------------------------------------

_KP_HANDLER_MAP: dict[str, object] = {
    "after_tmp_open": _install_kp_after_tmp_open,
    "mid_tmp_write": _install_kp_mid_tmp_write,
    "after_tmp_write": _install_kp_after_tmp_write,
    "after_tmp_fsync": _install_kp_after_tmp_fsync,
    "after_flock_acquire": _install_kp_after_flock_acquire,
    "after_rename": _install_kp_after_rename,
    "after_parent_dir_fsync": _install_kp_after_parent_dir_fsync,
    # KP10: recovery-of-recovery reuses KP3 (orphan .tmp left by prior kill)
    "recovery_of_recovery": _install_kp_after_tmp_write,
}

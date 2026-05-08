"""Per-step isolation tests for write_state_atomic protocol (AC1, Story 1.10)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        sys.platform == "win32", reason="POSIX-only — fcntl + signal semantics required"
    ),
]


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


@pytest.fixture()
def state():  # type: ignore[no-untyped-def]
    from sdlc.state.model import State

    return State(schema_version=1, next_monotonic_seq=42, epics={})


# ---------------------------------------------------------------------------
# Step 1: tmp file created after open
# ---------------------------------------------------------------------------
def test_step1_tmp_file_exists_after_open(target: Path, state: object) -> None:
    """After write_state_atomic_sync completes, the tmp file is gone (replaced)."""
    from sdlc.state.atomic import write_state_atomic_sync

    write_state_atomic_sync(state, target)  # type: ignore[arg-type]
    tmp = target.with_suffix(target.suffix + ".tmp")
    assert not tmp.exists(), "tmp file must be removed after successful rename"
    assert target.exists(), "target must exist after write"


# ---------------------------------------------------------------------------
# Step 2: content matches canonical bytes
# ---------------------------------------------------------------------------
def test_step2_content_matches_canonical_bytes(target: Path, state: object) -> None:
    from sdlc.state.atomic import _canonicalize_state, write_state_atomic_sync

    s = state  # type: ignore[assignment]
    write_state_atomic_sync(s, target)
    expected = _canonicalize_state(s)
    actual = target.read_bytes()
    assert actual == expected


# ---------------------------------------------------------------------------
# Step 3: os.fsync called on tmp fd
# ---------------------------------------------------------------------------
def test_step3_tmp_fsync_called(target: Path, state: object) -> None:
    from sdlc.state.atomic import write_state_atomic_sync

    fsync_calls: list[int] = []
    original_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        original_fsync(fd)

    with patch("sdlc.state.atomic.os.fsync", side_effect=recording_fsync):
        write_state_atomic_sync(state, target)  # type: ignore[arg-type]

    # At minimum 2 fsyncs: one for tmp fd, one for parent dir fd
    assert len(fsync_calls) >= 2, f"Expected ≥2 fsync calls, got {len(fsync_calls)}"


# ---------------------------------------------------------------------------
# Step 4: flock held during critical section (registry introspection)
# ---------------------------------------------------------------------------
def test_step4_flock_held_during_protocol(target: Path, state: object) -> None:
    """Lock registry must be empty before and after; held during execution."""
    from sdlc.concurrency import lock_registry
    from sdlc.state.atomic import write_state_atomic_sync

    held_during: list[bool] = []
    original_body = None

    import sdlc.state.atomic as _atomic

    def spy_body(s: object, t: object, sync_mode: bool = False) -> None:
        assert original_body is not None
        reg = lock_registry()
        held_during.append(len(reg) > 0)
        original_body(s, t, sync_mode)  # type: ignore[call-arg]

    original_body = _atomic._write_protocol_body  # type: ignore[assignment]
    with patch.object(_atomic, "_write_protocol_body", side_effect=spy_body):
        write_state_atomic_sync(state, target)  # type: ignore[arg-type]

    assert held_during, "spy never called"
    assert all(held_during), "lock must be held during protocol body"
    assert len(lock_registry()) == 0, "lock must be released after write"


# ---------------------------------------------------------------------------
# Step 5: target file replaced after rename
# ---------------------------------------------------------------------------
def test_step5_target_replaced_atomically(target: Path, state: object) -> None:
    from sdlc.state.atomic import write_state_atomic_sync
    from sdlc.state.model import State

    first = State(schema_version=1, next_monotonic_seq=1, epics={})
    write_state_atomic_sync(first, target)
    first_content = target.read_bytes()

    second = State(schema_version=1, next_monotonic_seq=2, epics={})
    write_state_atomic_sync(second, target)
    second_content = target.read_bytes()

    assert first_content != second_content, "Second write must replace the target"
    assert target.read_bytes() == second_content


# ---------------------------------------------------------------------------
# Step 6: parent directory fsync called
# ---------------------------------------------------------------------------
def test_step6_parent_dir_fsync_called(target: Path, state: object) -> None:
    from sdlc.state.atomic import write_state_atomic_sync

    dir_fsynced: list[bool] = []
    original_open = os.open
    original_fsync = os.fsync
    opened_dir_fds: set[int] = set()

    def recording_open(path: str, flags: int, mode: int = 0o777) -> int:
        fd = original_open(path, flags, mode)
        # NOTE: os.O_RDONLY == 0 on Linux/macOS, so `flags & os.O_RDONLY` is
        # always 0 (always falsy). The correct read-only check inspects the
        # access-mode bits via O_ACCMODE: only an exact O_RDONLY value passes.
        if path == str(target.parent) and (flags & os.O_ACCMODE) == os.O_RDONLY:
            opened_dir_fds.add(fd)
        return fd

    def recording_fsync(fd: int) -> None:
        if fd in opened_dir_fds:
            dir_fsynced.append(True)
        original_fsync(fd)

    with (
        patch("sdlc.state.atomic.os.open", side_effect=recording_open),
        patch("sdlc.state.atomic.os.fsync", side_effect=recording_fsync),
    ):
        write_state_atomic_sync(state, target)  # type: ignore[arg-type]

    assert dir_fsynced, "parent directory fd must be fsynced (Architecture §580)"


# ---------------------------------------------------------------------------
# Step 7: lock registry empty after write (flock released)
# ---------------------------------------------------------------------------
def test_step7_lock_released_after_write(target: Path, state: object) -> None:
    from sdlc.concurrency import lock_registry
    from sdlc.state.atomic import write_state_atomic_sync

    write_state_atomic_sync(state, target)  # type: ignore[arg-type]
    assert len(lock_registry()) == 0, "lock must be released after write completes"


# ---------------------------------------------------------------------------
# Async API: smoke test
# ---------------------------------------------------------------------------
def test_async_write_state_atomic(target: Path, state: object) -> None:
    from sdlc.state.atomic import write_state_atomic

    asyncio.run(write_state_atomic(state, target))  # type: ignore[arg-type]
    assert target.exists()


# ---------------------------------------------------------------------------
# StateError on relative path
# ---------------------------------------------------------------------------
def test_relative_path_raises_state_error() -> None:
    from sdlc.errors import StateError
    from sdlc.state.atomic import write_state_atomic_sync
    from sdlc.state.model import State

    s = State()
    with pytest.raises(StateError, match="absolute"):
        write_state_atomic_sync(s, Path("relative/state.json"))


# ---------------------------------------------------------------------------
# write_state_atomic_sync raises when called from event loop
# ---------------------------------------------------------------------------
async def _call_sync_from_loop(target: Path) -> None:
    from sdlc.state.atomic import write_state_atomic_sync
    from sdlc.state.model import State

    write_state_atomic_sync(State(), target)


def test_sync_from_event_loop_raises(target: Path) -> None:
    from sdlc.errors import StateError

    with pytest.raises(StateError, match="event loop"):
        asyncio.run(_call_sync_from_loop(target))

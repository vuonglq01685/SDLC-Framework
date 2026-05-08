"""Unit tests for sdlc.journal.writer — per-step isolation tests (AC1, Story 1.11)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

# Skip POSIX-only writer tests on Windows
_POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only writer")


def _make_entry(seq: int = 1) -> object:
    from sdlc.contracts.journal_entry import JournalEntry

    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts="2026-05-08T00:00:00.000Z",
        actor="test-actor",
        kind="state_mutation",
        target_id="target-001",
        before_hash=None,
        after_hash="sha256:" + "a" * 64,
        payload={"key": "value"},
    )


@_POSIX
def test_append_creates_file_when_missing(tmp_path: Path) -> None:
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    assert not journal.exists()
    append_sync(_make_entry(1), journal)
    assert journal.exists()
    lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


@_POSIX
def test_append_uses_o_append_flag(tmp_path: Path) -> None:
    """Verify os.open is called with O_WRONLY | O_CREAT | O_APPEND flags."""
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    captured_flags: list[int] = []
    original_open = os.open

    def fake_open(path: str, flags: int, mode: int = 0o777) -> int:
        if "journal.log" in str(path):
            captured_flags.append(flags)
        return original_open(path, flags, mode)

    with patch("sdlc.journal.writer.os.open", side_effect=fake_open):
        append_sync(_make_entry(1), journal)

    assert captured_flags, "os.open was not called with journal path"
    flags = captured_flags[0]
    assert (flags & os.O_ACCMODE) == os.O_WRONLY, "Expected O_WRONLY access mode"
    assert (flags & os.O_APPEND) != 0, "Expected O_APPEND flag"
    assert (flags & os.O_CREAT) != 0, "Expected O_CREAT flag"


@_POSIX
def test_append_canonical_bytes_match_model_dump(tmp_path: Path) -> None:
    from sdlc.journal import append_sync
    from sdlc.journal.writer import _canonicalize_entry

    entry = _make_entry(1)
    journal = tmp_path / "journal.log"
    append_sync(entry, journal)
    line = journal.read_bytes()
    assert line == _canonicalize_entry(entry)  # type: ignore[arg-type]


@_POSIX
def test_append_fsyncs_after_write(tmp_path: Path) -> None:
    """os.fsync must be called exactly once per append_sync call."""
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    fsync_calls: list[int] = []
    original_fsync = os.fsync

    def fake_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        original_fsync(fd)

    with patch("sdlc.journal.writer.os.fsync", side_effect=fake_fsync):
        append_sync(_make_entry(1), journal)

    assert len(fsync_calls) == 1


@_POSIX
def test_append_holds_flock_during_protocol(tmp_path: Path) -> None:
    """lock_registry() should contain the lock path while protocol body runs."""
    from sdlc.concurrency.locks import lock_registry
    from sdlc.journal import append_sync
    from sdlc.journal.writer import JOURNAL_LOCK_SUFFIX, _append_protocol_body

    journal = tmp_path / "journal.log"
    lock_path = str(journal.with_suffix(journal.suffix + JOURNAL_LOCK_SUFFIX).resolve())
    lock_held_during: list[bool] = []
    original_body = _append_protocol_body

    def spy_body(entry: object, path: Path) -> None:
        lock_held_during.append(lock_path in lock_registry())
        original_body(entry, path)  # type: ignore[arg-type]

    with patch("sdlc.journal.writer._append_protocol_body", side_effect=spy_body):
        append_sync(_make_entry(1), journal)

    assert lock_held_during == [True], "Lock should be held during protocol body"
    assert lock_path not in lock_registry(), "Lock should be released after protocol"


@_POSIX
def test_append_releases_flock_on_failure(tmp_path: Path) -> None:
    """Lock should NOT remain in registry after a failed append."""
    from sdlc.concurrency.locks import lock_registry
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync
    from sdlc.journal.writer import JOURNAL_LOCK_SUFFIX

    journal = tmp_path / "journal.log"
    lock_path = str(journal.with_suffix(journal.suffix + JOURNAL_LOCK_SUFFIX).resolve())

    with (
        patch("sdlc.journal.writer._canonicalize_entry", side_effect=ValueError("boom")),
        pytest.raises((ValueError, JournalError)),
    ):
        append_sync(_make_entry(1), journal)

    assert lock_path not in lock_registry(), "Lock leaked after failed append"


@_POSIX
def test_append_rejects_non_absolute_path() -> None:
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    with pytest.raises(JournalError) as exc:
        append_sync(_make_entry(1), Path("relative/journal.log"))
    assert exc.value.details.get("step") == "validate_path"


@_POSIX
def test_append_rejects_seq_regression(tmp_path: Path) -> None:
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    append_sync(_make_entry(5), journal)
    with pytest.raises(JournalError) as exc:
        append_sync(_make_entry(5), journal)
    assert exc.value.details.get("step") == "validate_seq"
    assert exc.value.details.get("expected_min") == 6


@_POSIX
def test_append_rejects_seq_equal_to_highest(tmp_path: Path) -> None:
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    append_sync(_make_entry(3), journal)
    with pytest.raises(JournalError) as exc:
        append_sync(_make_entry(3), journal)
    assert exc.value.details.get("step") == "validate_seq"


@_POSIX
def test_append_accepts_seq_strictly_greater(tmp_path: Path) -> None:
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    append_sync(_make_entry(5), journal)
    append_sync(_make_entry(6), journal)
    lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


@_POSIX
def test_append_sync_inside_event_loop_raises(tmp_path: Path) -> None:
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"

    async def _inner() -> None:
        with pytest.raises(JournalError) as exc:
            append_sync(_make_entry(1), journal)
        assert exc.value.details.get("step") == "loop_check"

    asyncio.run(_inner())


@_POSIX
def test_append_short_write_loop(tmp_path: Path) -> None:
    """When os.write returns half bytes on first call, loop retries and completes."""
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    call_count = [0]
    original_write = os.write

    def fake_write(fd: int, buf: bytes) -> int:
        call_count[0] += 1
        if call_count[0] == 1:
            half = max(1, len(buf) // 2)
            original_write(fd, buf[:half])
            return half
        return original_write(fd, buf)

    with patch("sdlc.journal.writer.os.write", side_effect=fake_write):
        append_sync(_make_entry(1), journal)

    assert call_count[0] >= 2, "Expected at least 2 write calls (short write retry)"
    assert journal.exists()


@_POSIX
def test_append_zero_byte_write_raises(tmp_path: Path) -> None:
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"

    with (
        patch("sdlc.journal.writer.os.write", return_value=0),
        pytest.raises(JournalError) as exc,
    ):
        append_sync(_make_entry(1), journal)
    assert exc.value.details.get("step") == "write_journal"


@_POSIX
def test_append_body_exception_preserved_over_close_oserror(tmp_path: Path) -> None:
    """Body OSError must bubble up; close OSError must NOT mask it."""
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    original_write = os.write
    write_count = [0]

    def raising_write(fd: int, buf: bytes) -> int:
        write_count[0] += 1
        if write_count[0] == 1:
            raise OSError(5, "Input/output error")  # EIO
        return original_write(fd, buf)

    original_close = os.close

    def raising_close(fd: int) -> None:
        original_close(fd)
        raise OSError(9, "Bad file descriptor")  # EBADF

    with (
        patch("sdlc.journal.writer.os.write", side_effect=raising_write),
        patch("sdlc.journal.writer.os.close", side_effect=raising_close),
        pytest.raises(OSError) as exc,
    ):
        append_sync(_make_entry(1), journal)
    # EIO (errno 5) must bubble up, not EBADF (errno 9)
    assert exc.value.errno == 5, f"Expected EIO(5), got errno {exc.value.errno}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows stub test only")
def test_append_cross_platform_stub_on_windows() -> None:
    """On Windows, sdlc.journal.append exists at import time but raises NotImplementedError."""
    import sdlc.journal as jmod

    assert hasattr(jmod, "append")
    with pytest.raises(NotImplementedError):
        asyncio.run(jmod.append(MagicMock(), Path("/some/path")))  # type: ignore[arg-type]

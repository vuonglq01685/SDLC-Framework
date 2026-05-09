"""POSIX append-only JSONL journal writer (FR31, Architecture §493 + §849-§851, NFR-REL-2).

O_APPEND-based atomic line semantics; flock serializes monotonic_seq validation. Helpers
split out (ADR-014 D1) into ``_canonical.py`` (canonicalization) and ``_seq.py`` (highest
seq scan) to keep this file ≤200 LOC.

``append_sync`` event-loop guard is bypassable from a worker thread spawned via
``loop.run_in_executor`` — same drift exists in ``state.atomic`` (deferred-work.md).
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    raise ImportError(
        "sdlc.journal.writer is POSIX-only — fcntl + O_APPEND semantics required"
        " (Architecture §573, §493)"
    )

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Final

from sdlc.concurrency import file_lock  # type: ignore[attr-defined]
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.journal._canonical import _canonicalize_entry, _normalize_strings  # noqa: F401
from sdlc.journal._seq import _read_highest_seq

_logger = logging.getLogger(__name__)

JOURNAL_LOCK_SUFFIX: Final[str] = ".lock"

# Drift detector: linter main() runtime-asserts hasattr(append/append_sync).
_CANONICAL_WRITE_API: Final[frozenset[str]] = frozenset(
    {"sdlc.journal.writer.append", "sdlc.journal.writer.append_sync"}
)


def _je(msg: str, **details: object) -> JournalError:
    """Build a JournalError; keeps raise sites compact."""
    return JournalError(msg, details=details)


def _lock_path_for(journal_path: Path) -> Path:
    if not journal_path.name:
        raise _je(
            "journal_path has empty name component — cannot derive lock path",
            path=str(journal_path),
            errno=None,
            step="validate_path",
        )
    if journal_path.suffix == JOURNAL_LOCK_SUFFIX:
        raise _je(
            "journal_path already ends in .lock — refusing to derive nested lock path",
            path=str(journal_path),
            errno=None,
            step="validate_path",
        )
    return Path(str(journal_path) + JOURNAL_LOCK_SUFFIX)


def _fsync_parent_dir(parent_dir: Path) -> None:
    """Mirrors ``state.atomic._fsync_parent_dir`` (lines 119-134); ADR-014 D2."""
    dir_fd: int | None = None
    try:
        dir_fd = os.open(str(parent_dir), os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError as e:
        raise _je(
            f"journal append failed at fsync parent dir: {e}",
            path=str(parent_dir),
            errno=e.errno,
            step="fsync_parent_dir",
        ) from e
    finally:
        if dir_fd is not None:
            with contextlib.suppress(OSError):
                os.close(dir_fd)


def _open_journal_for_append(journal_path: Path) -> tuple[int, bool]:
    existed_before_open = journal_path.exists()
    try:
        fd = os.open(str(journal_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as e:
        raise _je(
            f"journal append failed at open: {e}",
            path=str(journal_path),
            errno=e.errno,
            step="open_journal",
        ) from e
    return fd, existed_before_open


def _write_bytes_to_journal(fd: int, buf: bytes, journal_path: Path, seq: int) -> None:
    offset = 0
    while offset < len(buf):
        try:
            written = os.write(fd, buf[offset:])
        except OSError as e:
            raise _je(
                f"journal append failed at write: {e}",
                path=str(journal_path),
                errno=e.errno,
                step="write_journal",
                monotonic_seq=seq,
            ) from e
        if written <= 0:
            raise _je(
                "journal append failed: os.write returned non-positive byte count",
                path=str(journal_path),
                errno=None,
                step="write_invariant",
                monotonic_seq=seq,
                returned=written,
            )
        offset += written


def _fsync_journal(fd: int, journal_path: Path, seq: int) -> None:
    try:
        os.fsync(fd)
    except OSError as e:
        raise _je(
            f"journal append failed at fsync: {e}",
            path=str(journal_path),
            errno=e.errno,
            step="fsync_journal",
            monotonic_seq=seq,
        ) from e


def _verify_terminator(journal_path: Path) -> None:
    """Refuse to append when an existing non-empty file does not end in ``\\n``."""
    if not journal_path.exists():
        return
    size = journal_path.stat().st_size
    if size == 0:
        return
    fd = os.open(str(journal_path), os.O_RDONLY)
    try:
        os.lseek(fd, size - 1, os.SEEK_SET)
        last = os.read(fd, 1)
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
    if last != b"\n":
        raise _je(
            "journal terminator missing — last byte is not '\\n'; refusing to append",
            path=str(journal_path),
            errno=None,
            step="terminator_missing",
            size=size,
            last_byte_repr=repr(last),
        )


def _append_protocol_body(entry: JournalEntry, journal_path: Path) -> None:
    """Caller holds flock; runs the protocol (Architecture §581 step 8)."""
    seq = entry.monotonic_seq
    highest = _read_highest_seq(journal_path)
    if seq <= highest:
        raise _je(
            f"journal monotonic_seq regression: supplied {seq} <= highest {highest}",
            path=str(journal_path),
            errno=None,
            step="validate_seq",
            supplied=seq,
            expected_min=highest + 1,
            monotonic_seq=seq,
        )
    _verify_terminator(journal_path)
    canonical_bytes = _canonicalize_entry(entry)
    fd, existed_before_open = _open_journal_for_append(journal_path)
    body_exc: BaseException | None = None
    try:
        _write_bytes_to_journal(fd, canonical_bytes, journal_path, seq)
        _fsync_journal(fd, journal_path, seq)
    except BaseException as exc:
        body_exc = exc
        raise
    finally:
        try:
            os.close(fd)
        except OSError as close_exc:
            if body_exc is None:
                raise
            _logger.warning(
                "journal append: suppressed close OSError (errno=%s); preserving body"
                " exception (%s)",
                close_exc.errno,
                type(body_exc).__name__,
            )
    if not existed_before_open:
        _fsync_parent_dir(journal_path.parent)


def _validate_absolute(journal_path: Path, entry: JournalEntry, fn_name: str) -> None:
    if not journal_path.is_absolute():
        raise _je(
            f"journal.{fn_name} requires an absolute journal_path",
            path=str(journal_path),
            errno=None,
            step="validate_path",
            monotonic_seq=entry.monotonic_seq,
        )


async def append(entry: JournalEntry, journal_path: Path) -> None:
    """Async production API; offloads via ``asyncio.to_thread``."""
    _validate_absolute(journal_path, entry, "append")
    async with file_lock(_lock_path_for(journal_path)):
        await asyncio.to_thread(_append_protocol_body, entry, journal_path)


def append_sync(entry: JournalEntry, journal_path: Path) -> None:
    """Sync entrypoint for property/chaos tests with no event loop."""
    try:
        asyncio.get_running_loop()
        raise _je(
            "append_sync called from inside an event loop — use the async append instead",
            path=str(journal_path),
            errno=None,
            step="loop_check",
            monotonic_seq=entry.monotonic_seq,
        )
    except RuntimeError:
        pass
    _validate_absolute(journal_path, entry, "append_sync")
    with file_lock(_lock_path_for(journal_path)):
        _append_protocol_body(entry, journal_path)

"""Atomic raw-text write primitive (Epic 2A retro D1/C1, ADR-031).

Bridges the gap between ``state/atomic.py`` (state.json-specific, JSON-canonical) and the
17 ``Path.write_text()`` callsites scattered across ``cli/_*_pipeline.py`` plus
``dispatcher/_panel_helpers.py``. Same 7-step POSIX protocol as ``state/atomic.py``
PLUS explicit EINTR retry on ``os.write`` and ``os.replace``.

Lives under ``concurrency/`` (rather than ``engine/``) so both ``dispatcher/`` and
``cli/`` can import it — both depend on ``concurrency`` per the module-boundary table;
neither may import ``engine/``.

Closes ``EPIC-1-D3-EINTR-RETRY`` + ``EPIC-2A-D1-WRITE-PRIMITIVE``.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":  # pragma: no cover - POSIX-only invariant per Architecture §573
    raise ImportError(
        "sdlc.concurrency.io_primitives is POSIX-only — fcntl + parent-dir fsync are required"
    )

import contextlib
import errno
import os
from pathlib import Path
from typing import Final

# Re-exported for tests; mocks patch ``io_primitives.os.write`` /
# ``io_primitives.os.replace`` / ``io_primitives.os.open``.
__all__ = ["atomic_write", "atomic_write_bytes", "os"]

_TMP_SUFFIX: Final[str] = ".tmp"
_LOCK_SUFFIX: Final[str] = ".lock"

# EINTR retry budget for os.write and os.replace. 16 retries of a microsecond-
# scale syscall is well under any meaningful operator-visible latency. Beyond
# 16 EINTRs in sequence indicates a pathological signal-storm, not a
# recoverable interrupt.
_MAX_EINTR_RETRIES: Final[int] = 16

_OPEN_FLAGS: Final[int] = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC
_OPEN_MODE: Final[int] = 0o644


def _eintr_retry_write(fd: int, data: bytes) -> int:
    """Single ``os.write`` call with EINTR-retry up to ``_MAX_EINTR_RETRIES``."""
    last_eintr: OSError | None = None
    for _ in range(_MAX_EINTR_RETRIES + 1):
        try:
            return os.write(fd, data)
        except OSError as exc:
            if exc.errno != errno.EINTR:
                raise
            last_eintr = exc
    # Budget exhausted — surface the last EINTR.
    assert last_eintr is not None
    raise last_eintr


def _write_all(fd: int, payload: bytes) -> None:
    """Write the full ``payload`` to ``fd`` honouring short writes + EINTR."""
    offset = 0
    while offset < len(payload):
        written = _eintr_retry_write(fd, payload[offset:])
        if written == 0:
            # Blocking fd should never return 0 on a non-empty write; treat as fatal.
            raise OSError(errno.EIO, "os.write returned 0 bytes on a blocking fd")
        offset += written


def _eintr_retry_replace(src: str, dst: str) -> None:
    """Single ``os.replace`` call with EINTR-retry up to ``_MAX_EINTR_RETRIES``."""
    last_eintr: OSError | None = None
    for _ in range(_MAX_EINTR_RETRIES + 1):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if exc.errno != errno.EINTR:
                raise
            last_eintr = exc
    assert last_eintr is not None
    raise last_eintr


def _fsync_parent(parent_dir: str) -> None:
    """fsync the parent directory so the rename is visible after crash (POSIX)."""
    dir_fd = os.open(parent_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        with contextlib.suppress(OSError):
            os.close(dir_fd)


def _write_protocol_body(payload: bytes, target: Path) -> None:
    """7-step atomic-write protocol with EINTR retry on os.write + os.replace.

    Step 1 open tmp · 2 write · 3 fsync tmp · (4 flock — caller) · 5 rename · 6 fsync parent.
    """
    target_path = str(target)
    tmp_path = str(target.with_suffix(target.suffix + _TMP_SUFFIX))
    parent_dir = str(target.parent)

    tmp_fd = os.open(tmp_path, _OPEN_FLAGS, _OPEN_MODE)
    body_exc: BaseException | None = None
    try:
        _write_all(tmp_fd, payload)
        os.fsync(tmp_fd)
    except BaseException as exc:
        body_exc = exc
        # Best-effort cleanup of the tmp file so we don't leak.
        with contextlib.suppress(OSError):
            os.close(tmp_fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    finally:
        if body_exc is None:
            try:
                os.close(tmp_fd)
            except OSError:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise

    try:
        _eintr_retry_replace(tmp_path, target_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    _fsync_parent(parent_dir)


def atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically via tmp + rename + fsync (EINTR-safe).

    Caller responsibilities:
      - ``path`` must be absolute. ``ValueError`` on relative.
      - Parent directory must already exist. ``FileNotFoundError`` otherwise.
      - No concurrent writer holding the ``.lock`` sentinel (caller-managed).

    Raises:
      ValueError — relative path.
      OSError — propagated from the underlying syscalls (incl. EINTR-storm).
    """
    if not path.is_absolute():
        raise ValueError(f"atomic_write requires an absolute path, got: {path}")
    payload = content.encode(encoding)
    _write_protocol_body(payload, path)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Byte-oriented variant of :func:`atomic_write`."""
    if not path.is_absolute():
        raise ValueError(f"atomic_write_bytes requires an absolute path, got: {path}")
    _write_protocol_body(content, path)

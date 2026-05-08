"""Per-file flock context manager — POSIX-only (see Architecture §573).

Async path offloads blocking `fcntl.flock` via `asyncio.to_thread` (Architecture §727, Decision B2).
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    raise ImportError("sdlc.concurrency.locks is POSIX-only; fcntl is not available on Windows")

import asyncio
import fcntl
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

from sdlc.errors import DispatchError

_LOCK_REGISTRY: dict[str, int] = {}
_REGISTRY_LOCK: Final[threading.Lock] = threading.Lock()


def lock_registry() -> Mapping[str, int]:
    """Return a read-only snapshot of currently-held (path → fd) pairs."""
    with _REGISTRY_LOCK:
        return MappingProxyType(dict(_LOCK_REGISTRY))


class _FileLock:
    """Unified sync + async per-file exclusive lock (one class, two protocols)."""

    def __init__(self, path: str | Path) -> None:
        self._path: str = str(Path(path).resolve())
        self._fd: int | None = None

    def _open_fd(self) -> int:
        return os.open(self._path, os.O_CREAT | os.O_WRONLY, 0o666)

    def _flock_acquire_sync(self, fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as e:
            raise DispatchError(
                f"flock failed for {self._path}",
                details={"path": self._path, "errno": e.errno},
            ) from e

    async def _flock_acquire_async(self, fd: int) -> None:
        try:
            await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX)
        except OSError as e:
            raise DispatchError(
                f"flock failed for {self._path}",
                details={"path": self._path, "errno": e.errno},
            ) from e

    def _register(self, fd: int) -> None:
        with _REGISTRY_LOCK:
            _LOCK_REGISTRY[self._path] = fd

    def _release(self, body_exc: BaseException | None) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        with _REGISTRY_LOCK:
            _LOCK_REGISTRY.pop(self._path, None)
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            if body_exc is None:
                raise
        finally:
            try:
                os.close(fd)
            except OSError:
                if body_exc is None:
                    raise

    def __enter__(self) -> _FileLock:
        if self._fd is not None:
            raise DispatchError(
                f"_FileLock for {self._path} is not re-entrant",
                details={"path": self._path},
            )
        fd = self._open_fd()
        try:
            self._flock_acquire_sync(fd)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self._register(fd)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._release(exc_val)

    async def __aenter__(self) -> _FileLock:
        if self._fd is not None:
            raise DispatchError(
                f"_FileLock for {self._path} is not re-entrant",
                details={"path": self._path},
            )
        fd = self._open_fd()
        try:
            await self._flock_acquire_async(fd)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self._register(fd)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._release(exc_val)


def file_lock(path: str | Path) -> _FileLock:
    """Return a per-file exclusive lock context manager for *path*."""
    return _FileLock(path)

from __future__ import annotations

import asyncio
import errno
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("POSIX flock(2) only", allow_module_level=True)

import fcntl

from sdlc.concurrency.locks import file_lock, lock_registry
from sdlc.errors import DispatchError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock(2) only")


@pytest.mark.unit
class TestFileLockSync:
    def test_acquire_and_release_happy_path(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        with file_lock(lock_file):
            pass  # no exception raised

    def test_registry_contains_path_while_held(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())
        with file_lock(lock_file):
            registry = lock_registry()
            assert key in registry
            assert isinstance(registry[key], int)

    def test_registry_empty_after_release(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())
        with file_lock(lock_file):
            pass
        assert key not in lock_registry()

    def test_reacquire_after_release(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        with file_lock(lock_file):
            pass
        with file_lock(lock_file):
            pass  # second acquire succeeds without error

    def test_release_on_body_exception(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())
        with pytest.raises(ValueError, match="body error"), file_lock(lock_file):
            raise ValueError("body error")
        assert key not in lock_registry()

    def test_cross_process_contention(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        src_path = str(Path(__file__).resolve().parents[3] / "src")
        script = (
            f"import sys, time; sys.path.insert(0, {src_path!r}); "
            f"from sdlc.concurrency.locks import file_lock; "
            f"lk = file_lock({lock_file!r}); lk.__enter__(); "
            f"print('ACQUIRED', flush=True); time.sleep(1)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
        )
        assert proc.stdout is not None
        line = proc.stdout.readline()
        assert line.strip() == b"ACQUIRED", f"Child did not signal lock acquired: {line!r}"
        t1 = time.monotonic()
        with file_lock(lock_file):
            pass
        elapsed = time.monotonic() - t1
        proc.wait()
        assert elapsed > 0.1, f"Expected blocking wait; elapsed={elapsed:.3f}s"


@pytest.mark.unit
class TestFileLockAsync:
    def test_async_acquire_and_release(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")

        async def _run() -> None:
            async with file_lock(lock_file):
                pass

        asyncio.run(_run())

    def test_async_registry_contains_path_while_held(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())

        async def _run() -> None:
            async with file_lock(lock_file):
                registry = lock_registry()
                assert key in registry

        asyncio.run(_run())

    def test_async_registry_empty_after_release(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())

        async def _run() -> None:
            async with file_lock(lock_file):
                pass
            assert key not in lock_registry()

        asyncio.run(_run())

    def test_async_release_on_body_exception(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())

        async def _run() -> None:
            with pytest.raises(ValueError, match="async error"):
                async with file_lock(lock_file):
                    raise ValueError("async error")
            assert key not in lock_registry()

        asyncio.run(_run())

    def test_async_sync_parity(self, tmp_path: Path) -> None:
        """After async release, sync can acquire the same lock."""
        lock_file = str(tmp_path / "test.lock")

        async def _run() -> None:
            async with file_lock(lock_file):
                pass

        asyncio.run(_run())
        with file_lock(lock_file):
            pass


@pytest.mark.unit
class TestLockRegistry:
    def test_empty_when_no_locks_held(self) -> None:
        registry = lock_registry()
        assert isinstance(registry, Mapping)

    def test_returns_read_only_mapping(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        with file_lock(lock_file):
            registry = lock_registry()
            with pytest.raises((TypeError, AttributeError)):
                registry["fake"] = 999  # type: ignore[index]

    def test_mutation_does_not_affect_internal_state(self, tmp_path: Path) -> None:
        lock_file = str(tmp_path / "test.lock")
        key = str(Path(lock_file).resolve())
        with file_lock(lock_file):
            snapshot = dict(lock_registry())
            snapshot.pop(key, None)  # mutate the copy
            assert key in lock_registry()  # internal state unchanged


@pytest.mark.unit
class TestFileLockErrors:
    def test_dispatch_error_on_flock_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(fd: int, op: int) -> None:
            raise OSError(errno.ENOLCK, "No locks available")

        monkeypatch.setattr(fcntl, "flock", _raise)
        lock_file = str(tmp_path / "test.lock")
        with pytest.raises(DispatchError) as exc_info, file_lock(lock_file):
            pass
        assert "flock failed" in str(exc_info.value)
        assert exc_info.value.details.get("errno") == errno.ENOLCK

    def test_body_exception_preserved_when_close_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_close = os.close
        call_count: list[int] = [0]

        def _failing_close(fd: int) -> None:
            call_count[0] += 1
            original_close(fd)  # release the real fd to avoid leaks
            raise OSError("close failed")

        monkeypatch.setattr(os, "close", _failing_close)
        lock_file = str(tmp_path / "test.lock")
        with pytest.raises(ValueError, match="body error"), file_lock(lock_file):
            raise ValueError("body error")
        assert call_count[0] >= 1

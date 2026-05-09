"""POSIX atomic write protocol for state.json (Architecture §569-§589, Pattern §6, FR30, NFR-REL-1).

Full hash-verified read deferred to Story 1.11/1.12; read_state here is the minimum surface
needed for atomic-write chaos recovery assertions (no hash verification, no journal replay).
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    raise ImportError(
        "sdlc.state.atomic is POSIX-only — fcntl + parent-dir fsync are required"
        " (Architecture §573)"
    )

import asyncio
import contextlib
import json
import os
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from sdlc.concurrency import file_lock
from sdlc.errors import StateError
from sdlc.state.model import State

STATE_FILE_NAME: Final[str] = "state.json"
STATE_LOCK_SUFFIX: Final[str] = ".lock"
STATE_TMP_SUFFIX: Final[str] = ".tmp"

# Canonical write API names — intentional drift detector: if atomic.py renames
# either function, this constant breaks check_no_direct_state_writes.py.
_CANONICAL_WRITE_API: Final[frozenset[str]] = frozenset(
    {
        "sdlc.state.atomic.write_state_atomic",
        "sdlc.state.atomic.write_state_atomic_sync",
        "sdlc.state.atomic.write_state_raw_atomic_sync",
    }
)

_MIN_ARGS_FOR_OPEN = 2
_MIN_ARGS_FOR_RENAME = 2


def _normalize_strings(obj: Any) -> Any:
    """Recursively NFC-normalize all string values (Architecture §513)."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _normalize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_strings(item) for item in obj]
    return obj


def _canonicalize_state(state: State) -> bytes:
    """Return canonical JSON bytes for state (Architecture §501-§508).

    Terminating newline is POSIX-cleanliness convention; differs from hash-variant
    which omits newline per Architecture §513.
    """
    payload = _normalize_strings(state.model_dump(mode="json"))
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )


def _canonicalize_raw(payload: Mapping[str, object]) -> bytes:
    """Return canonical JSON bytes for a raw dict (Architecture §501-§508).

    Used by write_state_raw_atomic_sync to serialize post-migration state dicts
    whose schema_version may exceed what the State pydantic model knows about.
    """
    normalized = _normalize_strings(dict(payload))
    return (
        json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )


def _open_tmp(tmp_path: str, target_path: str) -> int:
    try:
        return os.open(tmp_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    except OSError as e:
        raise StateError(
            f"atomic write failed at step 1 (open tmp): {e}",
            details={"path": target_path, "errno": e.errno, "step": "open_tmp"},
        ) from e


def _write_bytes(tmp_fd: int, canonical_bytes: bytes, target_path: str) -> None:
    offset = 0
    while offset < len(canonical_bytes):
        try:
            written = os.write(tmp_fd, canonical_bytes[offset:])
        except OSError as e:
            raise StateError(
                f"atomic write failed at step 2 (write tmp): {e}",
                details={"path": target_path, "errno": e.errno, "step": "write_tmp"},
            ) from e
        if written == 0:
            # POSIX permits 0-byte returns when the descriptor is non-blocking and
            # the write would block; treat as fatal here because our fd is blocking.
            raise StateError(
                "atomic write failed at step 2 (write tmp): os.write returned 0 bytes",
                details={"path": target_path, "errno": 0, "step": "write_tmp"},
            )
        offset += written


def _fsync_fd(fd: int, step_name: str, target_path: str) -> None:
    try:
        os.fsync(fd)
    except OSError as e:
        raise StateError(
            f"atomic write failed at step 3/6 ({step_name}): {e}",
            details={"path": target_path, "errno": e.errno, "step": step_name},
        ) from e


def _rename(tmp_path: str, target_path: str) -> None:
    try:
        os.replace(tmp_path, target_path)
    except OSError as e:
        raise StateError(
            f"atomic write failed at step 5 (rename): {e}",
            details={"path": target_path, "errno": e.errno, "step": "rename"},
        ) from e


def _fsync_parent_dir(parent_dir: str, target_path: str) -> None:
    dir_fd: int | None = None
    try:
        dir_fd = os.open(parent_dir, os.O_RDONLY)
        _fsync_fd(dir_fd, "fsync_parent_dir", target_path)
    except StateError:
        raise
    except OSError as e:
        raise StateError(
            f"atomic write failed at step 6 (open parent dir): {e}",
            details={"path": target_path, "errno": e.errno, "step": "open_parent_dir"},
        ) from e
    finally:
        if dir_fd is not None:
            with contextlib.suppress(OSError):
                os.close(dir_fd)


def _write_protocol_body(canonical_bytes: bytes, target: Path) -> None:
    """Synchronous protocol body — single source of truth for the 7-step write protocol.

    Takes pre-canonicalized bytes; callers are responsible for canonicalization via
    _canonicalize_state or _canonicalize_raw.
    """
    target_path = str(target)
    tmp_path = str(target.with_suffix(target.suffix + STATE_TMP_SUFFIX))
    parent_dir = str(target.parent)

    # Step 1: open <target>.tmp
    tmp_fd = _open_tmp(tmp_path, target_path)

    body_exc: BaseException | None = None
    try:
        # Step 2: write canonical bytes (handle short writes)
        _write_bytes(tmp_fd, canonical_bytes, target_path)
        # Step 3: fsync tmp content for durability
        _fsync_fd(tmp_fd, "fsync_tmp", target_path)
    except BaseException as exc:
        body_exc = exc
        raise
    finally:
        try:
            os.close(tmp_fd)
        except OSError:
            if body_exc is None:
                raise

    # Step 5: atomic rename (lock acquired by caller wrapping this function)
    _rename(tmp_path, target_path)

    # Step 6: fsync parent directory — critical for OS-crash durability (Architecture §580)
    _fsync_parent_dir(parent_dir, target_path)


async def write_state_atomic(state: State, target: Path) -> None:
    """Write state atomically using the 7-step POSIX protocol (FR30, NFR-REL-1).

    Production async API. Uses file_lock for serialization and asyncio.to_thread
    for non-blocking fsync (Architecture §727).
    """
    if not target.is_absolute():
        raise StateError(
            "write_state_atomic requires an absolute target path",
            details={"path": str(target), "errno": 0, "step": "validate_path"},
        )
    lock_path = target.with_suffix(target.suffix + STATE_LOCK_SUFFIX)
    # Step 4: acquire flock (lock path is a sentinel file, NOT the target — Decision B2)
    async with file_lock(lock_path):
        canonical_bytes = _canonicalize_state(state)
        await asyncio.to_thread(_write_protocol_body, canonical_bytes, target)


def write_state_atomic_sync(state: State, target: Path) -> None:
    """Sync variant for chaos tests running in subprocess-killed children (no event loop).

    Do NOT call from production code paths — use write_state_atomic instead.
    """
    try:
        asyncio.get_running_loop()
        raise StateError(
            "write_state_atomic_sync called from inside an event loop"
            " — use the async write_state_atomic",
            details={"path": str(target), "errno": 0, "step": "loop_check"},
        )
    except RuntimeError:
        pass  # No running loop — safe to proceed

    if not target.is_absolute():
        raise StateError(
            "write_state_atomic_sync requires an absolute target path",
            details={"path": str(target), "errno": 0, "step": "validate_path"},
        )
    lock_path = target.with_suffix(target.suffix + STATE_LOCK_SUFFIX)
    # Step 4: acquire flock (sync variant)
    with file_lock(lock_path):
        canonical_bytes = _canonicalize_state(state)
        _write_protocol_body(canonical_bytes, target)


def write_state_raw_atomic_sync(payload: Mapping[str, object], target: Path) -> None:
    """Write a raw dict atomically using the 7-step POSIX protocol (Story 1.19, AC4).

    Bypasses pydantic and the schema gate — reserved for cli/migrate.py and
    state/rebuild.py (Story 1.20). The caller is responsible for ensuring the
    payload is semantically correct.

    Uses the same flock + atomic rename + fsync protocol as write_state_atomic_sync.
    """
    try:
        asyncio.get_running_loop()
        raise StateError(
            "write_state_raw_atomic_sync called from inside an event loop"
            " — use write_state_atomic for production paths",
            details={"path": str(target), "errno": 0, "step": "loop_check"},
        )
    except RuntimeError:
        pass  # No running loop — safe to proceed

    if not target.is_absolute():
        raise StateError(
            "write_state_raw_atomic_sync requires an absolute target path",
            details={"path": str(target), "errno": 0, "step": "validate_path"},
        )
    lock_path = target.with_suffix(target.suffix + STATE_LOCK_SUFFIX)
    with file_lock(lock_path):
        canonical_bytes = _canonicalize_raw(payload)
        _write_protocol_body(canonical_bytes, target)


# read_state moved to sdlc.state._read for cross-platform availability (Story 1.17 review).
# Re-exported here for backward compatibility with POSIX-side tests that import it directly.
# Story 1.19: _read.py now delegates to read_state_or_refuse so all callers get the schema gate.
from sdlc.state._read import read_state as read_state  # noqa: PLC0414, E402

"""POSIX append-only JSONL journal writer (FR31, Architecture §493 + §849-§851, NFR-REL-2).

O_APPEND-based atomic line semantics; flock serializes monotonic_seq validation.
Full hash-verified projection-from-journal deferred to Story 1.12.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    raise ImportError(
        "sdlc.journal.writer is POSIX-only — fcntl + O_APPEND semantics are required"
        " (Architecture §573, §493)"
    )

import asyncio
import json
import os
import unicodedata
from pathlib import Path
from typing import Any, Final

from sdlc.concurrency import file_lock
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError

JOURNAL_LOCK_SUFFIX: Final[str] = ".lock"

# Canonical write API names — intentional drift detector: if writer.py renames either
# function, this constant breaks check_no_journal_mutation.py.
_CANONICAL_WRITE_API: Final[frozenset[str]] = frozenset(
    {"sdlc.journal.writer.append", "sdlc.journal.writer.append_sync"}
)

_MIN_ARGS_FOR_OPEN = 2


def _normalize_strings(obj: Any) -> Any:
    """Recursively NFC-normalize all string values (Architecture §513).

    Duplicated from state/atomic.py:_normalize_strings to respect
    MODULE_DEPS["journal"].depends_on which excludes "state". Both copies must stay
    in lockstep — DO NOT factor up the dependency graph (out of v1 scope).
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _normalize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_strings(item) for item in obj]
    return obj


def _canonicalize_entry(entry: JournalEntry) -> bytes:
    """Return canonical JSONL bytes for a journal entry (Architecture §501-§508, §513).

    Terminating \\n is REQUIRED for JSONL — distinct from hash-canonicalization which omits it.
    """
    payload = _normalize_strings(entry.model_dump(mode="json"))
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )


def _read_highest_seq(journal_path: Path) -> int:
    """Return the maximum monotonic_seq across all parseable entries, or -1 if empty/missing.

    Caller must hold the write lock. Malformed lines are skipped with a stderr warning —
    the writer's validate_seq check is best-effort robustness; the property test asserts
    all written entries are well-formed.
    """
    if not journal_path.exists():
        return -1
    highest = -1
    try:
        with journal_path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = JournalEntry.model_validate_json(stripped)
                    highest = max(highest, entry.monotonic_seq)
                except (ValueError, TypeError) as e:
                    print(
                        f"warning: malformed journal line at {journal_path}:{lineno}: {e}"
                        " — skipping",
                        file=sys.stderr,
                    )
    except OSError as e:
        print(
            f"warning: could not read {journal_path} for seq check: {e} — treating as empty",
            file=sys.stderr,
        )
    return highest


def _open_journal_for_append(journal_path: Path) -> int:
    """Open journal file with O_WRONLY | O_CREAT | O_APPEND (atomic-to-EOF, kernel-enforced)."""
    try:
        # O_APPEND: POSIX guarantees each write(2) call is atomic to EOF.
        # NOT os.O_WRONLY + manual lseek — race-prone. NOT builtin open("a") — bypasses test-side
        # monkeypatching visibility and obscures the flags (mirrors state/atomic.py:69-71).
        return os.open(str(journal_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as e:
        raise JournalError(
            f"journal append failed at open: {e}",
            details={
                "path": str(journal_path),
                "errno": e.errno,
                "step": "open_journal",
            },
        ) from e


def _write_bytes_to_journal(fd: int, buf: bytes, journal_path: Path, seq: int) -> None:
    """Drain canonical bytes via short-write loop (mirrors state/atomic.py:_write_bytes)."""
    offset = 0
    while offset < len(buf):
        try:
            written = os.write(fd, buf[offset:])
        except OSError as e:
            raise JournalError(
                f"journal append failed at write: {e}",
                details={
                    "path": str(journal_path),
                    "errno": e.errno,
                    "step": "write_journal",
                    "monotonic_seq": seq,
                },
            ) from e
        if written == 0:
            raise JournalError(
                "journal append failed: os.write returned 0 bytes",
                details={
                    "path": str(journal_path),
                    "errno": 0,
                    "step": "write_journal",
                    "monotonic_seq": seq,
                },
            )
        offset += written


def _fsync_journal(fd: int, journal_path: Path, seq: int) -> None:
    try:
        os.fsync(fd)
    except OSError as e:
        raise JournalError(
            f"journal append failed at fsync: {e}",
            details={
                "path": str(journal_path),
                "errno": e.errno,
                "step": "fsync_journal",
                "monotonic_seq": seq,
            },
        ) from e


def _append_protocol_body(entry: JournalEntry, journal_path: Path) -> None:
    """Synchronous protocol body — single source of truth for the append protocol.

    Steps (Architecture §581 step 8):
    1. [lock held by caller] Read highest existing monotonic_seq.
    2. Validate entry.monotonic_seq > highest (lock serializes concurrent appenders).
    3. Canonicalize entry to bytes.
    4. open(O_WRONLY | O_CREAT | O_APPEND) — kernel-enforced atomic-to-EOF.
    5. Drain bytes via short-write loop.
    6. fsync for durability.
    7. close fd.
    Note: no parent-dir fsync — O_APPEND extends an existing inode in place; only the
    first-ever O_CREAT creates a new directory entry (v1 accepted gap; see ADR-014).
    """
    seq = entry.monotonic_seq

    # Step 2.5: monotonicity precondition (inside lock → serializes concurrent appenders)
    highest = _read_highest_seq(journal_path)
    if seq <= highest:
        raise JournalError(
            f"journal monotonic_seq regression: supplied {seq} <= highest {highest}",
            details={
                "path": str(journal_path),
                "step": "validate_seq",
                "supplied": seq,
                "expected_min": highest + 1,
                "monotonic_seq": seq,
            },
        )

    canonical_bytes = _canonicalize_entry(entry)

    fd = _open_journal_for_append(journal_path)
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
        except OSError:
            if body_exc is None:
                raise


async def append(entry: JournalEntry, journal_path: Path) -> None:
    """Append a JournalEntry to the journal using the POSIX O_APPEND protocol (FR31).

    Production async API. Uses file_lock for flock serialization and asyncio.to_thread
    to avoid blocking the event loop on fsync + linear seq scan (Architecture §727).
    """
    if not journal_path.is_absolute():
        raise JournalError(
            "journal.append requires an absolute journal_path",
            details={
                "path": str(journal_path),
                "errno": 0,
                "step": "validate_path",
                "monotonic_seq": entry.monotonic_seq,
            },
        )
    lock_path = journal_path.with_suffix(journal_path.suffix + JOURNAL_LOCK_SUFFIX)
    async with file_lock(lock_path):
        await asyncio.to_thread(_append_protocol_body, entry, journal_path)


def append_sync(entry: JournalEntry, journal_path: Path) -> None:
    """Sync entrypoint for property tests / chaos tests running in subprocess-killed children.

    Do NOT call from production code paths — use the async append.
    Raises JournalError if called from inside a running event loop (footgun guard mirroring
    state.atomic.write_state_atomic_sync).
    """
    try:
        asyncio.get_running_loop()
        raise JournalError(
            "append_sync called from inside an event loop — use the async append instead",
            details={
                "path": str(journal_path),
                "errno": 0,
                "step": "loop_check",
                "monotonic_seq": entry.monotonic_seq,
            },
        )
    except RuntimeError:
        pass  # No running loop — safe to proceed

    if not journal_path.is_absolute():
        raise JournalError(
            "journal.append_sync requires an absolute journal_path",
            details={
                "path": str(journal_path),
                "errno": 0,
                "step": "validate_path",
                "monotonic_seq": entry.monotonic_seq,
            },
        )
    lock_path = journal_path.with_suffix(journal_path.suffix + JOURNAL_LOCK_SUFFIX)
    with file_lock(lock_path):
        _append_protocol_body(entry, journal_path)

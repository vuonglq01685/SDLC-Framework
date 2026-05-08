"""Story 1.11 review patches — tests added during code-review remediation.

Lifted from ``test_journal_append_protocol.py`` to keep that file ≤400 LOC
(NFR-MAINT-3 / Architecture §765). Covers terminator-missing rejection, parent-dir
fsync on first create, and ``_lock_path_for`` validation edge cases.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

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
def test_append_rejects_missing_terminator(tmp_path: Path) -> None:
    """Existing non-empty journal whose last byte != '\\n' rejects further appends.

    Closes torn-write / glue-line / blank-line corruption windows (review patches
    Edge B1 / H4 / H5).
    """
    from sdlc.errors import JournalError
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    # Write a valid first entry, then truncate the trailing newline to simulate corruption.
    append_sync(_make_entry(1), journal)
    raw = journal.read_bytes()
    assert raw.endswith(b"\n")
    fd = os.open(str(journal), os.O_WRONLY)
    try:
        os.ftruncate(fd, len(raw) - 1)
    finally:
        os.close(fd)
    with pytest.raises(JournalError) as exc:
        append_sync(_make_entry(2), journal)
    details = exc.value.details
    assert details.get("step") == "terminator_missing"
    assert details.get("size") == len(raw) - 1
    assert "last_byte_repr" in details


@_POSIX
def test_append_fsyncs_parent_dir_on_first_create(tmp_path: Path) -> None:
    """First-ever ``O_CREAT`` triggers parent-dir fsync; subsequent appends do not."""
    from sdlc.journal import append_sync

    journal = tmp_path / "journal.log"
    fsync_fds: list[int] = []
    parent_dir_fds: set[int] = set()
    original_open = os.open
    original_fsync = os.fsync

    def tracking_open(path: object, flags: int, mode: int = 0o777) -> int:
        fd = original_open(path, flags, mode)  # type: ignore[arg-type]
        if str(path) == str(tmp_path):
            parent_dir_fds.add(fd)
        return fd

    def tracking_fsync(fd: int) -> None:
        fsync_fds.append(fd)
        original_fsync(fd)

    with (
        patch("sdlc.journal.writer.os.open", side_effect=tracking_open),
        patch("sdlc.journal.writer.os.fsync", side_effect=tracking_fsync),
    ):
        append_sync(_make_entry(1), journal)
    assert any(fd in parent_dir_fds for fd in fsync_fds), (
        "Parent dir fsync missing on first-create; review patch D2"
    )
    fsync_fds.clear()
    parent_dir_fds.clear()

    with (
        patch("sdlc.journal.writer.os.open", side_effect=tracking_open),
        patch("sdlc.journal.writer.os.fsync", side_effect=tracking_fsync),
    ):
        append_sync(_make_entry(2), journal)
    assert not any(fd in parent_dir_fds for fd in fsync_fds), (
        "Parent dir fsync should NOT happen for non-create appends"
    )


@_POSIX
def test_lock_path_for_rejects_empty_name(tmp_path: Path) -> None:
    """``_lock_path_for`` validates name + suffix BEFORE concatenating (Blind H1 + Edge H6)."""
    from sdlc.errors import JournalError
    from sdlc.journal.writer import _lock_path_for

    with pytest.raises(JournalError) as exc:
        _lock_path_for(Path("/"))
    assert exc.value.details.get("step") == "validate_path"

    with pytest.raises(JournalError) as exc2:
        _lock_path_for(tmp_path / "j.lock")
    assert exc2.value.details.get("step") == "validate_path"


@_POSIX
def test_lock_path_for_string_concat(tmp_path: Path) -> None:
    """Plain string concat — no ``with_suffix`` edge cases on dotted names."""
    from sdlc.journal.writer import _lock_path_for

    journal = tmp_path / "audit.events.log"
    lp = _lock_path_for(journal)
    assert str(lp) == str(journal) + ".lock"

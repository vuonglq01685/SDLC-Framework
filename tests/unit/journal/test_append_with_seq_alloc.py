"""Unit tests for journal.append_with_seq_alloc (C2 / Epic 2A retro D2).

RED phase per CONTRIBUTING §2 — tests cover the atomic-allocate-and-append
contract: returns the allocated seq, monotonic across sequential calls,
factory exception leaves journal unchanged, factory-produced seq mismatch
rejected, relative-path rejected.

GREEN lands in a follow-up commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Module under test is POSIX-only (writer.py raises ImportError on Windows).
if sys.platform == "win32":  # pragma: no cover
    pytest.skip("journal writer is POSIX-only", allow_module_level=True)

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError
from sdlc.journal import append_with_seq_alloc

_ZERO_HASH = "sha256:" + "0" * 64


def _make_entry(seq: int) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts="2026-05-21T00:00:00Z",
        actor="test",
        kind="run_command",
        target_id="t",
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload={},
    )


@pytest.mark.unit
class TestAppendWithSeqAlloc:
    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_journal(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.log"
        seq = await append_with_seq_alloc(journal, _make_entry)
        assert seq == 0

    @pytest.mark.asyncio
    async def test_increments_from_existing_seq(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.log"
        await append_with_seq_alloc(journal, _make_entry)
        await append_with_seq_alloc(journal, _make_entry)
        seq3 = await append_with_seq_alloc(journal, _make_entry)
        assert seq3 == 2

    @pytest.mark.asyncio
    async def test_factory_receives_allocated_seq(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.log"
        seen: list[int] = []

        def factory(seq: int) -> JournalEntry:
            seen.append(seq)
            return _make_entry(seq)

        await append_with_seq_alloc(journal, factory)
        await append_with_seq_alloc(journal, factory)
        assert seen == [0, 1]

    @pytest.mark.asyncio
    async def test_factory_seq_mismatch_rejected(self, tmp_path: Path) -> None:
        """If the factory builds an entry whose monotonic_seq does NOT equal the
        allocated value, the protocol body's seq<=highest invariant fires and
        the append is rejected — no partial write."""
        journal = tmp_path / "journal.log"
        # First call seeds the journal at seq=0.
        await append_with_seq_alloc(journal, _make_entry)

        def bad_factory(seq: int) -> JournalEntry:
            # Return a stale seq that already exists on disk.
            return _make_entry(0)

        with pytest.raises(JournalError):
            await append_with_seq_alloc(journal, bad_factory)

    @pytest.mark.asyncio
    async def test_factory_exception_propagates_no_partial_write(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.log"
        await append_with_seq_alloc(journal, _make_entry)  # seed at 0
        size_before = journal.stat().st_size

        def boom(seq: int) -> JournalEntry:
            raise RuntimeError("factory failed")

        with pytest.raises(RuntimeError, match="factory failed"):
            await append_with_seq_alloc(journal, boom)
        # Journal must not have grown.
        assert journal.stat().st_size == size_before

    @pytest.mark.asyncio
    async def test_relative_path_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(JournalError, match="absolute"):
            await append_with_seq_alloc(Path("relative.log"), _make_entry)

    @pytest.mark.asyncio
    async def test_sequential_calls_produce_monotonic_seqs(self, tmp_path: Path) -> None:
        journal = tmp_path / "journal.log"
        seqs: list[int] = []
        for _ in range(5):
            seqs.append(await append_with_seq_alloc(journal, _make_entry))
        assert seqs == [0, 1, 2, 3, 4]

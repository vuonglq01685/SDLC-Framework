"""Unit tests for sdlc.journal.reader — iter_entries + iter_after (AC1/AC2, Story 1.11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _make_entry_json(seq: int, actor: str = "test") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "monotonic_seq": seq,
            "ts": "2026-05-08T00:00:00.000Z",
            "actor": actor,
            "kind": "state_mutation",
            "target_id": "t-001",
            "before_hash": None,
            "after_hash": "sha256:" + "b" * 64,
            "payload": {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_iter_entries_empty_file_yields_nothing(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    journal.write_text("", encoding="utf-8")
    assert list(iter_entries(journal)) == []


def test_iter_entries_missing_file_yields_nothing(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "nonexistent.log"
    assert list(iter_entries(journal)) == []


def test_iter_entries_yields_in_file_order(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(0), _make_entry_json(1), _make_entry_json(2)])
    entries = list(iter_entries(journal))
    assert len(entries) == 3
    assert [e.monotonic_seq for e in entries] == [0, 1, 2]


def test_iter_entries_raises_on_seq_regression(tmp_path: Path) -> None:
    """Hand-crafted file with seq 0, 1, 0 — third line regression triggers JournalError."""
    from sdlc.errors import JournalError
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    # Write 0, 1, 0 — bypassing the writer's validate_seq
    _write_lines(
        journal,
        [_make_entry_json(0), _make_entry_json(1), _make_entry_json(0)],
    )
    with pytest.raises(JournalError) as exc:
        list(iter_entries(journal))
    assert exc.value.details.get("step") == "reader_invariant"


def test_iter_entries_skips_malformed_lines_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed lines: skipped + WARNING log emitted (review fix Blind L5)."""
    import logging

    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(0), "not json", _make_entry_json(2)])
    with caplog.at_level(logging.WARNING, logger="sdlc.journal.reader"):
        entries = list(iter_entries(journal))
    assert len(entries) == 2
    assert entries[0].monotonic_seq == 0
    assert entries[1].monotonic_seq == 2
    assert any("malformed journal line" in rec.message for rec in caplog.records), (
        f"Expected WARNING log on malformed line; got: {[r.message for r in caplog.records]}"
    )


def test_iter_after_filters_strictly_greater(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_after

    journal = tmp_path / "journal.log"
    _write_lines(
        journal,
        [_make_entry_json(0), _make_entry_json(1), _make_entry_json(2), _make_entry_json(3)],
    )
    result = list(iter_after(journal, threshold=1))
    assert [e.monotonic_seq for e in result] == [2, 3]


def test_iter_after_threshold_above_all(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_after

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(0), _make_entry_json(1)])
    assert list(iter_after(journal, threshold=99)) == []


def test_iter_after_threshold_below_all(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_after

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(5), _make_entry_json(10)])
    result = list(iter_after(journal, threshold=-1))
    assert len(result) == 2


def test_iter_after_rejects_non_int_threshold(tmp_path: Path) -> None:
    """``iter_after`` validates the threshold type up-front (review fix Edge M5)."""
    from sdlc.errors import JournalError
    from sdlc.journal.reader import iter_after

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(0)])
    with pytest.raises(JournalError) as exc:
        list(iter_after(journal, threshold="5"))  # type: ignore[arg-type]
    assert exc.value.details.get("step") == "validate_threshold"


def test_iter_entries_works_on_windows(tmp_path: Path) -> None:
    """Reader has no POSIX-only guard — must work cross-platform."""
    # This test is NOT skipped on Windows (unlike the writer tests)
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    _write_lines(journal, [_make_entry_json(0), _make_entry_json(1)])
    entries = list(iter_entries(journal))
    assert len(entries) == 2


def test_iter_entries_skips_blank_lines(tmp_path: Path) -> None:
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    # Write valid entries with blank lines interspersed
    journal.write_text(
        _make_entry_json(0) + "\n\n" + _make_entry_json(1) + "\n",
        encoding="utf-8",
    )
    entries = list(iter_entries(journal))
    assert len(entries) == 2
    assert [e.monotonic_seq for e in entries] == [0, 1]


def test_iter_entries_raises_journal_error_on_oserror(tmp_path: Path) -> None:
    from unittest.mock import patch

    from sdlc.errors import JournalError
    from sdlc.journal.reader import iter_entries

    journal = tmp_path / "journal.log"
    journal.write_text("", encoding="utf-8")
    with (
        patch("pathlib.Path.open", side_effect=OSError(5, "Input/output error")),
        pytest.raises(JournalError) as exc,
    ):
        list(iter_entries(journal))
    assert exc.value.details.get("step") == "read_journal"

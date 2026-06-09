"""Tests for _poll_journal / _poll_agent_runs helpers in sdlc.cli.logs (Story 1.18.1).

B-P10: All echo captures use monkeypatch.setattr — no hand-rolled try/finally.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from sdlc.contracts.journal_entry import JournalEntry

from .conftest import EXIT_SYSTEM_ERROR, EXIT_USER_ERROR, make_ctx  # noqa: F401

pytestmark = pytest.mark.unit


def _make_journal_entry(seq: int, ts: str, target_id: str = "state") -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor="cli",
        kind="scan_completed",
        target_id=target_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload={},
    )


def test_logs_poll_journal_missing_file(tmp_path: Path) -> None:
    """_poll_journal returns unchanged pos when journal file does not exist."""
    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()
    _, pos = _poll_journal(tmp_path / "nonexistent.log", 0, None, None, json_mode=False, ctx=ctx)
    assert pos == 0


def test_logs_poll_journal_no_new_data(tmp_path: Path) -> None:
    """_poll_journal returns unchanged pos when journal hasn't grown."""
    journal = tmp_path / "journal.log"
    journal.write_text(_make_journal_entry(0, "2026-01-01T00:00:00Z").model_dump_json() + "\n")
    file_size = journal.stat().st_size
    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()
    _, pos = _poll_journal(journal, file_size, None, None, json_mode=False, ctx=ctx)
    assert pos == file_size


def test_logs_poll_journal_blank_malformed_and_filtered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """_poll_journal: blank lines skipped; malformed lines warned; non-matching filtered."""
    journal = tmp_path / "journal.log"
    good = _make_journal_entry(0, "2026-01-01T00:00:00Z", target_id="EPIC-other-S01-x-T01-y")
    journal.write_text("\nNOT JSON\n" + good.model_dump_json() + "\n")
    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()
    with caplog.at_level(logging.WARNING):
        _poll_journal(journal, 0, "EPIC-foo-S01-bar-T01-baz", None, json_mode=False, ctx=ctx)
    assert "malformed journal line" in caplog.text
    captured = capsys.readouterr()
    assert captured.out == ""


def test_logs_poll_journal_matching_entry_emitted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """_poll_journal emits matching entries and returns updated file position."""
    journal = tmp_path / "journal.log"
    journal.write_text(_make_journal_entry(0, "2026-01-01T00:00:00Z").model_dump_json() + "\n")
    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()
    _, new_pos = _poll_journal(journal, 0, None, None, json_mode=False, ctx=ctx)
    assert new_pos > 0
    captured = capsys.readouterr()
    assert "scan_completed" in captured.out


def test_logs_poll_agent_runs_missing_file(tmp_path: Path) -> None:
    """_poll_agent_runs returns 0 when file does not exist."""
    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()
    _, pos = _poll_agent_runs(
        tmp_path / "nonexistent.jsonl", 0, None, None, json_mode=False, ctx=ctx
    )
    assert pos == 0


def test_logs_poll_agent_runs_no_new_data(tmp_path: Path) -> None:
    """_poll_agent_runs returns unchanged pos when file size hasn't grown."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    content = json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x"}) + "\n"
    runs.write_text(content)
    file_size = runs.stat().st_size
    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()
    _, pos = _poll_agent_runs(runs, file_size, None, None, json_mode=False, ctx=ctx)
    assert pos == file_size


def test_logs_poll_agent_runs_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """_poll_agent_runs emits matching records and returns new file position."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "state"}) + "\n"
    )
    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()
    _, new_pos = _poll_agent_runs(runs, 0, None, None, json_mode=False, ctx=ctx)
    assert new_pos > 0
    captured = capsys.readouterr()
    assert "agent_run/x" in captured.out


def test_logs_poll_agent_runs_filter_and_malformed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """_poll_agent_runs skips non-matching records; warns on malformed JSON; handles non-dict."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        "NOT JSON\n"
        + "[1,2]\n"
        + json.dumps(
            {"ts": "2026-01-01T00:00:00Z", "agent": "other", "target_id": "EPIC-x-S01-y-T01-z"}
        )
        + "\n"
    )
    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()
    with caplog.at_level(logging.WARNING):
        _poll_agent_runs(runs, 0, "EPIC-foo-S01-bar-T01-baz", None, json_mode=False, ctx=ctx)
    assert "malformed agent_runs line" in caplog.text
    assert capsys.readouterr().out == ""


def test_logs_poll_agent_runs_blank_lines_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """_poll_agent_runs skips blank lines without emitting or erroring."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        "\n"
        + json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "state"})
        + "\n\n"
    )
    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()
    _poll_agent_runs(runs, 0, None, None, json_mode=False, ctx=ctx)
    captured = capsys.readouterr()
    assert "agent_run/x" in captured.out


# ---------------------------------------------------------------------------
# AC4: rotation and truncation detection (inode tracking)
# ---------------------------------------------------------------------------


def test_logs_poll_journal_rotation_detected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC4: _poll_journal resets pos to 0 and warns when inode changes (rotation)."""
    journal = tmp_path / "journal.log"
    entry = _make_journal_entry(0, "2026-01-01T00:00:00Z")
    journal.write_text(entry.model_dump_json() + "\n")

    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()

    # First poll: capture real inode.
    first_inode, first_pos = _poll_journal(journal, 0, None, None, json_mode=False, ctx=ctx)
    assert first_pos > 0

    # Simulate rotation the way logrotate does: rename the old file aside (it keeps
    # the original inode) so the freshly created journal is GUARANTEED a new inode.
    # A bare unlink()+create can reuse the just-freed inode on Linux ext4 (the macOS
    # dev FS hid this), leaving new_inode == first_inode and masking the rotation.
    journal.rename(journal.with_name(journal.name + ".1"))
    entry2 = _make_journal_entry(1, "2026-01-01T00:00:01Z")
    journal.write_text(entry2.model_dump_json() + "\n")

    with caplog.at_level(logging.WARNING):
        new_inode, new_pos = _poll_journal(
            journal, first_pos, None, None, json_mode=False, ctx=ctx, inode=first_inode
        )

    assert new_inode != first_inode, "new file should have a different inode"
    assert new_pos > 0, "new entry should have been consumed"
    assert "rotated" in caplog.text


def test_logs_poll_journal_truncation_detected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC4: _poll_journal resets pos to 0 and warns when file size shrinks (truncation)."""
    journal = tmp_path / "journal.log"
    entry = _make_journal_entry(0, "2026-01-01T00:00:00Z")
    journal.write_text(entry.model_dump_json() + "\n")

    from sdlc.cli.logs import _poll_journal

    ctx = make_ctx()

    first_inode, first_pos = _poll_journal(journal, 0, None, None, json_mode=False, ctx=ctx)
    assert first_pos > 0

    # Simulate truncation: write a shorter file with same inode.
    journal.write_text("")  # truncate to 0

    with caplog.at_level(logging.WARNING):
        _new_inode, new_pos = _poll_journal(
            journal, first_pos, None, None, json_mode=False, ctx=ctx, inode=first_inode
        )

    assert new_pos == 0, "pos should reset to 0 after truncation"
    assert "truncated" in caplog.text


def test_logs_poll_agent_runs_rotation_detected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC4: _poll_agent_runs resets pos to 0 and warns when inode changes (rotation)."""
    runs = tmp_path / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "state"}) + "\n"
    )

    from sdlc.cli.logs import _poll_agent_runs

    ctx = make_ctx()

    first_inode, first_pos = _poll_agent_runs(runs, 0, None, None, json_mode=False, ctx=ctx)
    assert first_pos > 0

    # Rotate via rename (logrotate-style): the old inode stays allocated to the
    # renamed file, so the new file gets a fresh inode. A bare unlink()+create can
    # reuse the freed inode on Linux ext4 and mask the rotation (see journal test).
    runs.rename(runs.with_name(runs.name + ".1"))
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "agent": "y", "target_id": "state"}) + "\n"
    )

    with caplog.at_level(logging.WARNING):
        new_inode, _new_pos = _poll_agent_runs(
            runs, first_pos, None, None, json_mode=False, ctx=ctx, inode=first_inode
        )

    assert new_inode != first_inode
    assert "rotated" in caplog.text

"""Tests for _poll_journal / _poll_agent_runs helpers in sdlc.cli.logs (Story 1.18)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> Any:
    import typer

    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


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

    ctx = _make_ctx()
    result = _poll_journal(tmp_path / "nonexistent.log", 0, None, None, json_mode=False, ctx=ctx)
    assert result == 0


def test_logs_poll_journal_no_new_data(tmp_path: Path) -> None:
    """_poll_journal returns unchanged pos when journal hasn't grown."""
    journal = tmp_path / "journal.log"
    journal.write_text(_make_journal_entry(0, "2026-01-01T00:00:00Z").model_dump_json() + "\n")
    file_size = journal.stat().st_size
    from sdlc.cli.logs import _poll_journal

    ctx = _make_ctx()
    result = _poll_journal(journal, file_size, None, None, json_mode=False, ctx=ctx)
    assert result == file_size


def test_logs_poll_journal_blank_malformed_and_filtered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_poll_journal: blank lines skipped; malformed lines warned; non-matching filtered."""
    journal = tmp_path / "journal.log"
    good = _make_journal_entry(0, "2026-01-01T00:00:00Z", target_id="EPIC-other-S01-x-T01-y")
    journal.write_text("\nNOT JSON\n" + good.model_dump_json() + "\n")
    from sdlc.cli.logs import _poll_journal

    ctx = _make_ctx()
    emitted: list[str] = []
    from sdlc.cli import logs as _logs_mod

    orig = _logs_mod.echo

    def _cap(msg: str, *, err: bool = False, ctx: Any = None) -> None:
        emitted.append(msg)

    _logs_mod.echo = _cap  # type: ignore[assignment]
    try:
        with caplog.at_level(logging.WARNING):
            _poll_journal(
                journal,
                0,
                "EPIC-foo-S01-bar-T01-baz",
                None,
                json_mode=False,
                ctx=ctx,
            )
    finally:
        _logs_mod.echo = orig  # type: ignore[assignment]
    assert "malformed journal line" in caplog.text
    assert emitted == []


def test_logs_poll_journal_matching_entry_emitted(tmp_path: Path) -> None:
    """_poll_journal emits matching entries and returns updated file position."""
    journal = tmp_path / "journal.log"
    journal.write_text(_make_journal_entry(0, "2026-01-01T00:00:00Z").model_dump_json() + "\n")
    from sdlc.cli.logs import _poll_journal

    ctx = _make_ctx()
    emitted: list[str] = []
    from sdlc.cli import logs as _logs_mod

    orig = _logs_mod.echo

    def _cap(msg: str, *, err: bool = False, ctx: Any = None) -> None:
        emitted.append(msg)

    _logs_mod.echo = _cap  # type: ignore[assignment]
    try:
        new_pos = _poll_journal(journal, 0, None, None, json_mode=False, ctx=ctx)
    finally:
        _logs_mod.echo = orig  # type: ignore[assignment]
    assert new_pos > 0
    assert any("scan_completed" in line for line in emitted)


def test_logs_poll_agent_runs_missing_file(tmp_path: Path) -> None:
    """_poll_agent_runs returns 0 when file does not exist."""
    from sdlc.cli.logs import _poll_agent_runs

    ctx = _make_ctx()
    result = _poll_agent_runs(
        tmp_path / "nonexistent.jsonl", 0, None, None, json_mode=False, ctx=ctx
    )
    assert result == 0


def test_logs_poll_agent_runs_no_new_data(tmp_path: Path) -> None:
    """_poll_agent_runs returns unchanged pos when file size hasn't grown."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    content = json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x"}) + "\n"
    runs.write_text(content)
    file_size = runs.stat().st_size
    from sdlc.cli.logs import _poll_agent_runs

    ctx = _make_ctx()
    result = _poll_agent_runs(runs, file_size, None, None, json_mode=False, ctx=ctx)
    assert result == file_size


def test_logs_poll_agent_runs_basic(tmp_path: Path) -> None:
    """_poll_agent_runs emits matching records and returns new file position."""
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "state"}) + "\n"
    )
    from sdlc.cli.logs import _poll_agent_runs

    ctx = _make_ctx()
    emitted: list[str] = []
    from sdlc.cli import logs as _logs_mod

    orig = _logs_mod.echo

    def _cap(msg: str, *, err: bool = False, ctx: Any = None) -> None:
        emitted.append(msg)

    _logs_mod.echo = _cap  # type: ignore[assignment]
    try:
        new_pos = _poll_agent_runs(runs, 0, None, None, json_mode=False, ctx=ctx)
    finally:
        _logs_mod.echo = orig  # type: ignore[assignment]
    assert new_pos > 0
    assert any("agent_run/x" in line for line in emitted)


def test_logs_poll_agent_runs_filter_and_malformed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
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

    ctx = _make_ctx()
    emitted: list[str] = []
    from sdlc.cli import logs as _logs_mod

    orig = _logs_mod.echo

    def _cap(msg: str, *, err: bool = False, ctx: Any = None) -> None:
        emitted.append(msg)

    _logs_mod.echo = _cap  # type: ignore[assignment]
    try:
        with caplog.at_level(logging.WARNING):
            _poll_agent_runs(runs, 0, "EPIC-foo-S01-bar-T01-baz", None, json_mode=False, ctx=ctx)
    finally:
        _logs_mod.echo = orig  # type: ignore[assignment]
    assert "malformed agent_runs line" in caplog.text
    assert emitted == []


def test_logs_poll_agent_runs_blank_lines_skipped(tmp_path: Path) -> None:
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

    ctx = _make_ctx()
    emitted: list[str] = []
    from sdlc.cli import logs as _logs_mod

    orig = _logs_mod.echo

    def _cap(msg: str, *, err: bool = False, ctx: Any = None) -> None:
        emitted.append(msg)

    _logs_mod.echo = _cap  # type: ignore[assignment]
    try:
        _poll_agent_runs(runs, 0, None, None, json_mode=False, ctx=ctx)
    finally:
        _logs_mod.echo = orig  # type: ignore[assignment]
    assert any("agent_run/x" in line for line in emitted)

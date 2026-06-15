"""Trace correlation_id reconstruction tests (Story 4.1, AC4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli.trace import collect_entries_by_correlation_id
from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit


def _append(journal: Path, entry: JournalEntry) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def test_collect_entries_by_correlation_id(tmp_path: Path) -> None:
    journal = tmp_path / "journal.log"
    cid = "11111111-2222-3333-4444-555555555555"
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=0,
            ts="2026-06-10T10:00:00.000Z",
            actor="auto_loop",
            kind="auto_loop_iteration",
            target_id="auto-loop-iter-1",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={"iteration_seq": 1, "action": "dispatch", "correlation_id": cid},
        ),
    )
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=1,
            ts="2026-06-10T10:00:01.000Z",
            actor="dispatcher",
            kind="dispatch_attempt",
            target_id="task",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={"correlation_id": cid, "outcome": "success"},
        ),
    )
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=2,
            ts="2026-06-10T10:00:02.000Z",
            actor="auto_loop",
            kind="auto_loop_iteration",
            target_id="auto-loop-iter-2",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={"iteration_seq": 2, "action": "stopped", "correlation_id": "other"},
        ),
    )

    matched = collect_entries_by_correlation_id(journal, cid)
    assert len(matched) == 2
    assert all(e.payload.get("correlation_id") == cid for e in matched)


_CID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _seed_correlation_journal(tmp_path: Path) -> Path:
    """Initialized project with a journal: two entries under _CID + one under another id."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}", encoding="utf-8")
    journal = state_dir / "journal.log"
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=0,
            ts="2026-06-10T10:00:00.000Z",
            actor="auto_loop",
            kind="auto_loop_iteration",
            target_id="auto-loop-iter-1",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={
                "iteration_seq": 1,
                "action": "dispatch",
                "correlation_id": _CID,
                "task_id": "T",
            },
        ),
    )
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=1,
            ts="2026-06-10T10:00:01.000Z",
            actor="dispatcher",
            kind="dispatch_attempt",
            target_id="task",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={"correlation_id": _CID, "outcome": "success"},
        ),
    )
    _append(
        journal,
        JournalEntry(
            schema_version=1,
            monotonic_seq=2,
            ts="2026-06-10T10:00:02.000Z",
            actor="auto_loop",
            kind="auto_loop_iteration",
            target_id="auto-loop-iter-2",
            before_hash=None,
            after_hash="sha256:" + "0" * 64,
            payload={"iteration_seq": 2, "action": "stopped", "correlation_id": "other"},
        ),
    )
    return journal


def test_trace_command_reconstructs_iteration_by_correlation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json

    from typer.testing import CliRunner

    from sdlc.cli.main import app

    _seed_correlation_journal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app, ["--json", "trace", "--correlation-id", _CID], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert payload["command"] == "trace"
    assert payload["correlation_id"] == _CID
    assert payload["event_count"] == 2
    # Chronological (monotonic_seq order); the "other" cid entry is excluded.
    assert [e["kind"] for e in payload["events"]] == ["auto_loop_iteration", "dispatch_attempt"]
    assert all(e["payload"]["correlation_id"] == _CID for e in payload["events"])


def test_trace_command_correlation_human_and_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from sdlc.cli.main import app

    _seed_correlation_journal(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    human = runner.invoke(app, ["trace", "--correlation-id", _CID], catch_exceptions=False)
    assert human.exit_code == 0, human.output
    assert "2 events" in human.output
    assert "auto_loop_iteration" in human.output

    empty = runner.invoke(app, ["trace", "--correlation-id", "no-such-id"], catch_exceptions=False)
    assert empty.exit_code == 0, empty.output
    assert "0 events" in empty.output


def test_trace_command_rejects_both_selectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from sdlc.cli.main import app

    _seed_correlation_journal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["trace", "EPIC-foo-S01-bar-T01-baz", "--correlation-id", _CID],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert "exactly one" in result.output.lower()

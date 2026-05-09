"""Unit tests for sdlc.cli.logs (Story 1.18.1 quality hardening).

B-P21: time.monotonic budget replaced with sentinel monkeypatch on _follow_streams.
B-P29: normal CliRunner import.
B-P30: JSON envelope assertion for --filter-task invalid path.
"""

from __future__ import annotations

import contextlib
import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner  # B-P29: normal import

from sdlc.cli.main import app
from sdlc.contracts.journal_entry import JournalEntry

from .conftest import EXIT_USER_ERROR

pytestmark = pytest.mark.unit

runner = CliRunner()


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def _make_entry(
    seq: int,
    ts: str,
    *,
    target_id: str = "state",
    actor: str = "cli",
    kind: str = "scan_completed",
    payload: dict[str, Any] | None = None,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=actor,
        kind=kind,
        target_id=target_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload=payload or {},
    )


def _bootstrap_project(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}")
    journal = state_dir / "journal.log"
    journal.touch()
    return journal


def _append_entry(journal: Path, entry: JournalEntry) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def test_logs_refuses_when_state_not_initialized(tmp_path: Path) -> None:
    result = runner.invoke(app, ["logs"], catch_exceptions=False)
    assert result.exit_code == 1


def test_logs_prints_all_entries_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(3):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:0{i}Z"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    stdout = out.getvalue()
    assert stdout.count("journal/scan_completed") == 3


def test_logs_filter_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    target = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target))
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:01Z", target_id=target))
    _append_entry(journal, _make_entry(2, "2026-01-01T00:00:02Z", target_id="EPIC-x-S01-y-T01-z"))
    _append_entry(journal, _make_entry(3, "2026-01-01T00:00:03Z", target_id="EPIC-x-S01-y-T01-w"))
    _append_entry(journal, _make_entry(4, "2026-01-01T00:00:04Z", target_id="EPIC-x-S01-y-T01-v"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=target, filter_agent=None, follow=False)
    stdout = out.getvalue()
    assert stdout.count("[journal/") == 2


def test_logs_filter_task_invalid_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task="not-a-task-id", filter_agent=None, follow=False)
    assert exc_info.value.exit_code == EXIT_USER_ERROR


def test_logs_filter_task_invalid_id_json_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """B-P30: JSON mode for invalid --filter-task emits error.code == 'ERR_USER_INPUT' on stderr."""
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task="not-a-task-id", filter_agent=None, follow=False)
    assert exc_info.value.exit_code == EXIT_USER_ERROR
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["error"]["code"] == "ERR_USER_INPUT"


@pytest.mark.parametrize("bad_agent", ["", "   "])
def test_logs_filter_agent_empty_rejected(
    bad_agent: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P3: empty or whitespace-only --filter-agent → ERR_USER_INPUT exit 1."""
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=bad_agent, follow=False)
    assert exc_info.value.exit_code == EXIT_USER_ERROR


def test_logs_filter_agent_journal_actor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    _append_entry(
        journal,
        _make_entry(0, "2026-01-01T00:00:00Z", actor="agent:implementer"),
    )
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:01Z", actor="cli"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent="implementer", follow=False)
    assert out.getvalue().count("[journal/") == 1


def test_logs_filter_agent_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    _append_entry(
        journal,
        _make_entry(0, "2026-01-01T00:00:00Z", actor="cli", payload={"agent": "researcher"}),
    )
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:01Z", actor="cli"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent="researcher", follow=False)
    assert out.getvalue().count("[journal/") == 1


def test_logs_filter_agent_runs_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "implementer", "target_id": "state"})
        + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent="implementer", follow=False)
    assert "[agent_run/implementer]" in out.getvalue()


def test_logs_combined_filters_and_logic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    target = "EPIC-foo-S01-bar-T01-baz"
    # Matches task AND agent
    _append_entry(
        journal,
        _make_entry(0, "2026-01-01T00:00:00Z", target_id=target, actor="agent:implementer"),
    )
    # Matches task only
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:01Z", target_id=target, actor="cli"))
    # Matches agent only
    _append_entry(
        journal,
        _make_entry(
            2, "2026-01-01T00:00:02Z", target_id="EPIC-x-S01-y-T01-z", actor="agent:implementer"
        ),
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=target, filter_agent="implementer", follow=False)
    assert out.getvalue().count("[journal/") == 1


def test_logs_chronological_merge_with_agent_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _bootstrap_project(tmp_path)
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z"))
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:02Z"))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "agent": "x", "target_id": "state"}) + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    payload = json.loads(out.getvalue())
    tss = [e["ts"] for e in payload["events"]]
    assert tss == sorted(tss)
    sources = [e["source"] for e in payload["events"]]
    assert sources == ["journal", "agent_runs", "journal"]


def test_logs_json_mode_envelope_keys_no_follow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    payload = json.loads(out.getvalue())
    assert set(payload.keys()) == {"command", "filters", "events", "event_count"}


def test_logs_json_filters_block_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    target = "EPIC-foo-S01-bar-T01-baz"
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=target, filter_agent=None, follow=False)
    payload = json.loads(out.getvalue())
    assert payload["filters"]["task_id"] == target
    assert payload["filters"]["agent"] is None


def test_logs_no_follow_returns_after_streams_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P21: sentinel proves no follow-mode entered — no wall-clock budget."""
    journal = _bootstrap_project(tmp_path)
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    # If _follow_streams is ever called, the test fails immediately.
    monkeypatch.setattr(
        logs, "_follow_streams", lambda *a, **kw: pytest.fail("entered follow-mode unexpectedly")
    )
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    # Should have printed 1 event without entering follow mode.
    assert "scan_completed" in out.getvalue()

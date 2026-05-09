"""Unit tests for sdlc.cli.trace (Story 1.18, AC7.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.contracts.journal_entry import JournalEntry

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
    """Create minimal initialized project structure."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}")
    journal = state_dir / "journal.log"
    journal.touch()
    return journal


def _append_entry(journal: Path, entry: JournalEntry) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def test_trace_refuses_when_state_not_initialized(tmp_path: Path) -> None:
    result = runner.invoke(app, ["trace", "EPIC-foo-S01-bar-T01-baz"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "not initialized" in result.output.lower() or "not initialized" in (result.stderr or "")


def test_trace_rejects_invalid_task_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    import typer as _typer

    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(_typer.Exit) as exc_info:
        trace.run_trace(ctx=ctx, task_id="not-a-task-id")
    assert exc_info.value.exit_code == 1


def test_trace_empty_journal_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id="EPIC-foo-S01-bar-T01-baz")
    assert "0 events" in out.getvalue()


def test_trace_filters_by_target_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    _append_entry(
        journal, _make_entry(1, "2026-01-01T00:00:01Z", target_id="EPIC-other-S01-x-T01-y")
    )
    _append_entry(
        journal, _make_entry(2, "2026-01-01T00:00:02Z", target_id="EPIC-other-S01-x-T01-z")
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    stdout = out.getvalue()
    assert "1 events" in stdout
    assert target_task in stdout


def test_trace_filters_by_payload_task_id_for_agent_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(
        journal,
        _make_entry(
            0,
            "2026-01-01T00:00:00Z",
            target_id="something-else",
            kind="agent_dispatch",
            payload={"task_id": target_task, "agent": "implementer"},
        ),
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "1 events" in out.getvalue()


def test_trace_includes_agent_runs_jsonl_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "target_id": target_task, "agent": "impl"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T00:00:02Z", "target_id": "EPIC-other-S01-x-T01-y"})
        + "\n"
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "2 events" in out.getvalue()


def test_trace_handles_missing_agent_runs_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "1 events" in out.getvalue()


def test_trace_skips_malformed_agent_runs_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "target_id": target_task})
        + "\n"
        + "NOT VALID JSON\n"
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    import logging

    with caplog.at_level(logging.WARNING):
        import contextlib
        from io import StringIO

        out = StringIO()
        with contextlib.redirect_stdout(out):
            trace.run_trace(ctx=ctx, task_id=target_task)
    assert "malformed agent_runs line" in caplog.text
    assert "2 events" in out.getvalue()


def test_trace_chronological_sort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    _append_entry(journal, _make_entry(1, "2026-01-01T00:00:02Z", target_id=target_task))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    runs = impl_dir / "agent_runs.jsonl"
    runs.write_text(
        json.dumps({"ts": "2026-01-01T00:00:01Z", "target_id": target_task, "agent": "x"}) + "\n"
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    payload = json.loads(out.getvalue())
    tss = [e["ts"] for e in payload["events"]]
    assert tss == sorted(tss)
    assert payload["events"][0]["source"] == "journal"
    assert payload["events"][1]["source"] == "agent_runs"
    assert payload["events"][2]["source"] == "journal"


def test_trace_json_mode_envelope_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    payload = json.loads(out.getvalue())
    assert set(payload.keys()) == {"command", "task_id", "project_root", "events", "event_count"}


def test_trace_json_empty_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    import contextlib
    from io import StringIO

    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id="EPIC-foo-S01-bar-T01-baz")
    payload = json.loads(out.getvalue())
    assert payload["events"] == []
    assert payload["event_count"] == 0

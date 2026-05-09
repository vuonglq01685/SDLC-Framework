"""Branch-coverage tests for sdlc.cli.logs — filter/emit/error paths (Story 1.18)."""

from __future__ import annotations

import contextlib
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import typer

from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit


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


def test_logs_iter_agent_runs_blank_and_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Blank lines skipped; malformed JSON lines emit WARNING and are skipped."""
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        "\n"
        + "NOT JSON\n"
        + json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "state"})
        + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with caplog.at_level(logging.WARNING), contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert "malformed agent_runs line" in caplog.text
    assert "[agent_run/x]" in out.getvalue()


def test_logs_iter_agent_runs_nonobject_json_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Non-dict JSON values emit WARNING and are skipped."""
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text("[1, 2, 3]\n")
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with caplog.at_level(logging.WARNING), contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert "non-object agent_runs line" in caplog.text
    assert out.getvalue() == ""


def test_logs_iter_agent_runs_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Directory in place of agent_runs.jsonl raises OSError → exit 2."""
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").mkdir()
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert exc_info.value.exit_code == 2


def test_logs_agent_run_task_filter_no_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """agent_run whose target_id/task_id doesn't match filter_task is skipped."""
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": "EPIC-x-S01-y-T01-z"})
        + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(
            ctx=ctx,
            filter_task="EPIC-foo-S01-bar-T01-baz",
            filter_agent=None,
            follow=False,
        )
    assert out.getvalue() == ""


def test_logs_agent_run_without_ts_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """agent_run record without a string ts is silently skipped."""
    _bootstrap_project(tmp_path)
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        json.dumps({"agent": "x", "target_id": "state"}) + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert out.getvalue() == ""


def test_logs_json_follow_historical_ndjson_has_command_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P6/B-P7: --follow --json historical events are NDJSON and carry command == "logs".

    Each historical event line is emitted via _emit_event, which adds the
    `command` field so consumers see one consistent shape across the
    historical→live transition (ADR-021).
    """
    journal = _bootstrap_project(tmp_path)
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z"))
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_follow_streams", lambda *_a, **_kw: None)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(typer.Exit):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["source"] == "journal"
    assert obj.get("command") == "logs"  # B-P6: consistent NDJSON shape


def test_logs_load_events_journal_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JournalError from _collect_logs → emit_error → exit 2."""
    from sdlc.errors import JournalError

    _bootstrap_project(tmp_path)

    def _raise(**_kw: Any) -> list[dict[str, Any]]:
        raise JournalError("corrupted")

    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_collect_logs", _raise)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert exc_info.value.exit_code == 2


def test_logs_load_events_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError from _collect_logs → emit_error → exit 2."""
    _bootstrap_project(tmp_path)

    def _raise(**_kw: Any) -> list[dict[str, Any]]:
        raise OSError("disk error")

    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_collect_logs", _raise)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=False)
    assert exc_info.value.exit_code == 2


def test_logs_agent_run_filter_task_match_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """agent_run whose target_id matches filter_task is included."""
    _bootstrap_project(tmp_path)
    target = "EPIC-foo-S01-bar-T01-baz"
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "agent": "x", "target_id": target}) + "\n"
    )
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        logs.run_logs(ctx=ctx, filter_task=target, filter_agent=None, follow=False)
    assert "[agent_run/x]" in out.getvalue()

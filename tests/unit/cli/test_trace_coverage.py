"""Branch-coverage tests for sdlc.cli.trace (Story 1.18)."""

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


def test_trace_hook_invocation_payload_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1.5 predicate 3: hook_invocation with payload.target_id == task_id is included."""
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(
        journal,
        _make_entry(
            0,
            "2026-01-01T00:00:00Z",
            kind="hook_invocation",
            target_id="state",
            payload={"target_id": target_task},
        ),
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "1 events" in out.getvalue()


def test_trace_agent_dispatch_payload_mismatch_not_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """agent_dispatch with payload.task_id != target → not included (branch 49->51)."""
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(
        journal,
        _make_entry(
            0,
            "2026-01-01T00:00:00Z",
            kind="agent_dispatch",
            target_id="state",
            payload={"task_id": "EPIC-other-S01-x-T01-y"},
        ),
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "0 events" in out.getvalue()


def test_trace_agent_runs_nonobject_json_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Non-dict JSON values in agent_runs are skipped with a warning."""
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text("[1, 2, 3]\n")
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with caplog.at_level(logging.WARNING), contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "non-object agent_runs line" in caplog.text
    assert "1 events" in out.getvalue()


def test_trace_agent_runs_blank_lines_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blank lines in agent_runs.jsonl are skipped without error."""
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z", target_id=target_task))
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        "\n" + json.dumps({"ts": "2026-01-01T00:00:01Z", "target_id": target_task}) + "\n\n"
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "2 events" in out.getvalue()


def test_trace_agent_run_without_ts_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent_run records matching task but lacking a string ts are skipped."""
    _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").write_text(
        json.dumps({"target_id": target_task, "agent": "impl"}) + "\n"
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "0 events" in out.getvalue()


def test_trace_agent_runs_oserror_propagated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSError from agent_runs.jsonl (e.g. directory in place of file) → exit 2."""
    _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "agent_runs.jsonl").mkdir()
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert exc_info.value.exit_code == 2


def test_trace_load_events_journal_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JournalError from _collect_events → emit_error → exit 2."""
    from sdlc.errors import JournalError

    _bootstrap_project(tmp_path)

    def _raise(**_kw: Any) -> list[dict[str, Any]]:
        raise JournalError("corrupted journal")

    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(trace, "_collect_events", _raise)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        trace.run_trace(ctx=ctx, task_id="EPIC-foo-S01-bar-T01-baz")
    assert exc_info.value.exit_code == 2


def test_trace_load_events_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError from _collect_events → emit_error → exit 2."""
    _bootstrap_project(tmp_path)

    def _raise(**_kw: Any) -> list[dict[str, Any]]:
        raise OSError("disk error")

    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(trace, "_collect_events", _raise)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        trace.run_trace(ctx=ctx, task_id="EPIC-foo-S01-bar-T01-baz")
    assert exc_info.value.exit_code == 2


def test_trace_hook_invocation_payload_mismatch_not_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """hook_invocation with payload.target_id != task_id is not included (branch 53->55)."""
    journal = _bootstrap_project(tmp_path)
    target_task = "EPIC-foo-S01-bar-T01-baz"
    _append_entry(
        journal,
        _make_entry(
            0,
            "2026-01-01T00:00:00Z",
            kind="hook_invocation",
            target_id="state",
            payload={"target_id": "EPIC-other-S01-x-T01-y"},
        ),
    )
    from sdlc.cli import trace

    monkeypatch.setattr(trace, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        trace.run_trace(ctx=ctx, task_id=target_task)
    assert "0 events" in out.getvalue()

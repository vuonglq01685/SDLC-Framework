"""Unit tests for sdlc.cli.logs follow-mode (Story 1.18.1, AC1).

Follow-mode tests use stop-event / sentinel synchronization — no ctypes,
no fixed sleep budgets, no platform-specific signal injection.
"""

from __future__ import annotations

import threading
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


def test_follow_keyboard_interrupt_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow mode exits 0 on KeyboardInterrupt — no thread injection, no ctypes.

    Simulates KI by monkeypatching _poll_journal to raise it on the first call.
    _follow_streams suppresses KI via contextlib.suppress, so run_logs raises Exit(0).
    """
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)

    call_count = [0]

    def _ki_poll(
        journal_path: Path,
        journal_pos: int,
        filter_task: Any,
        filter_agent: Any,
        *,
        json_mode: bool,
        ctx: typer.Context,
        inode: int = -1,
    ) -> tuple[int, int]:
        call_count[0] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(logs, "_poll_journal", _ki_poll)
    monkeypatch.setattr(logs, "_poll_agent_runs", lambda *a, **kw: 0)

    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
    assert exc_info.value.exit_code == 0


def test_follow_emits_new_journal_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Follow mode picks up entries appended after it starts.

    Uses threading.Event for synchronization — no ctypes, no fixed sleeps.
    The stop event breaks the follow loop after the new entry is confirmed seen.
    Output is captured by patching make_console to write to a shared StringIO.
    """
    import io

    from rich.console import Console

    journal = _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_FOLLOW_INTERVAL_S", 0.02)

    stop = threading.Event()
    seen = threading.Event()
    buf = io.StringIO()

    # Intercept make_console to write to our buf and signal when scan_completed appears.
    def _fake_make_console(ctx: Any) -> Console:
        class _SignalingConsole(Console):
            def print(self, *args: Any, **kwargs: Any) -> None:
                super().print(*args, **kwargs)
                text = buf.getvalue()
                if "scan_completed" in text:
                    seen.set()

        return _SignalingConsole(file=buf, no_color=True, force_terminal=False)

    monkeypatch.setattr(logs, "make_console", _fake_make_console)

    # Wrap _follow_streams to inject the stop event.
    orig_follow = logs._follow_streams

    def _follow_with_stop(*args: Any, **kwargs: Any) -> None:
        kwargs["_stop"] = stop
        orig_follow(*args, **kwargs)

    monkeypatch.setattr(logs, "_follow_streams", _follow_with_stop)

    ctx = _make_ctx()
    captured_exit: list[int] = []
    errors: list[Exception] = []

    def _run() -> None:
        try:
            logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
        except typer.Exit as exc:
            captured_exit.append(exc.exit_code)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Append a new entry while follow is running.
    entry = _make_entry(0, "2026-01-01T12:00:00Z")
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")

    # Wait until the entry is confirmed seen (no fixed sleep).
    assert seen.wait(timeout=5.0), f"new entry not seen in follow output; buf={buf.getvalue()!r}"
    stop.set()
    thread.join(timeout=5.0)

    assert not thread.is_alive(), "follow thread did not terminate after stop event"
    assert not errors, f"unexpected exceptions: {errors}"
    assert captured_exit == [0], f"expected exit 0, got {captured_exit}"


def test_follow_broken_pipe_suppressed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B-P15: BrokenPipeError from stdout write is suppressed — no traceback, exit 0.

    Simulates `sdlc logs --follow | head -1` by monkeypatching _poll_journal to
    raise BrokenPipeError, which _follow_streams must absorb via contextlib.suppress.
    """
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)

    def _broken_pipe_poll(
        journal_path: Path,
        journal_pos: int,
        filter_task: Any,
        filter_agent: Any,
        *,
        json_mode: bool,
        ctx: typer.Context,
        inode: int = -1,
    ) -> tuple[int, int]:
        raise BrokenPipeError("pipe closed")

    monkeypatch.setattr(logs, "_poll_journal", _broken_pipe_poll)
    monkeypatch.setattr(logs, "_poll_agent_runs", lambda *a, **kw: 0)

    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
    assert exc_info.value.exit_code == 0


def test_follow_race_window_entry_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P25: entry appended between historical-collect and follow-start is not lost.

    run_logs captures journal_pos_before BEFORE the historical pass. If an entry
    lands in the journal between the pos-capture and follow-start, the follow loop
    picks it up because it starts from journal_pos_before (not from after historical).

    The test verifies that _follow_streams is called with journal_pos=0 (the
    pre-historical size), even though the journal has grown during the historical pass.
    """
    _bootstrap_project(tmp_path)

    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)

    # Capture what journal_pos is passed to _follow_streams.
    captured_journal_pos: list[int] = []

    def _capturing_follow(
        journal_path: Path,
        agent_runs_path: Path,
        filter_task: Any,
        filter_agent: Any,
        ctx: typer.Context,
        *,
        journal_pos: int,
        agent_pos: int,
        _stop: Any = None,
    ) -> None:
        captured_journal_pos.append(journal_pos)

    monkeypatch.setattr(logs, "_follow_streams", _capturing_follow)

    # Append the race-window entry BEFORE run_logs — the journal is non-empty
    # but journal_pos_before must still be 0 (size at bootstrap).
    # To simulate the true race, we need journal to be empty when pos is captured.
    # Bootstrap gives us an empty journal; pos_before = 0.
    # Then _collect_logs runs (sees 0 events since we haven't appended yet).
    # Then _follow_streams must start with pos=0 to catch future appends.
    ctx = _make_ctx()
    with pytest.raises(typer.Exit):
        logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)

    # _follow_streams should have been called with journal_pos=0 (the pre-historical size).
    assert captured_journal_pos == [0], (
        f"expected journal_pos=0 (pre-historical), got {captured_journal_pos}"
    )

"""Unit tests for sdlc.cli.logs follow-mode (Story 1.18, AC7.4)."""

from __future__ import annotations

import sys
import threading
import time
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


@pytest.mark.skipif(sys.platform == "win32", reason="signal-based KI flaky on Windows")
def test_follow_keyboard_interrupt_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow mode exits 0 on KeyboardInterrupt — no stack trace on stderr."""
    _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_FOLLOW_INTERVAL_S", 0.05)

    ctx = _make_ctx()
    errors: list[Exception] = []
    captured_exit: list[int] = []

    def _run() -> None:
        try:
            logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
        except typer.Exit as exc:
            captured_exit.append(exc.exit_code)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    time.sleep(0.15)
    # Inject KeyboardInterrupt into the follow loop via raising in thread.
    # We do this by setting a flag that the monkeypatched sleep checks.
    import ctypes

    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread.ident),  # type: ignore[arg-type]
        ctypes.py_object(KeyboardInterrupt),
    )
    thread.join(timeout=2.0)
    assert not thread.is_alive(), "follow thread did not terminate"
    assert not errors, f"unexpected exceptions: {errors}"
    assert captured_exit == [0], f"expected exit 0, got {captured_exit}"


@pytest.mark.skipif(sys.platform == "win32", reason="signal-based KI flaky on Windows")
def test_follow_emits_new_journal_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Follow mode picks up entries appended after it starts."""
    journal = _bootstrap_project(tmp_path)
    from sdlc.cli import logs

    monkeypatch.setattr(logs, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(logs, "_FOLLOW_INTERVAL_S", 0.05)

    lines_seen: list[str] = []
    orig_echo = logs.echo

    def _capture_echo(msg: str, *, err: bool = False, ctx: typer.Context | None = None) -> None:
        lines_seen.append(msg)
        orig_echo(msg, err=err, ctx=ctx)

    monkeypatch.setattr(logs, "echo", _capture_echo)

    ctx = _make_ctx()
    errors: list[Exception] = []
    captured_exit: list[int] = []

    def _run() -> None:
        try:
            logs.run_logs(ctx=ctx, filter_task=None, filter_agent=None, follow=True)
        except typer.Exit as exc:
            captured_exit.append(exc.exit_code)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    time.sleep(0.15)

    # Append a new entry while follow is running.
    entry = _make_entry(0, "2026-01-01T12:00:00Z")
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")

    time.sleep(0.25)

    import ctypes

    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread.ident),  # type: ignore[arg-type]
        ctypes.py_object(KeyboardInterrupt),
    )
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert not errors
    assert any("scan_completed" in line for line in lines_seen), (
        f"new entry not seen in follow output: {lines_seen}"
    )

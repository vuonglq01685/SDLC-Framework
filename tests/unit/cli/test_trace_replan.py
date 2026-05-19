"""Unit tests: sdlc trace global-event passthrough for replan_invalidated (Story 2A.19, Task 4.2).

AC6/D1: any sdlc trace <task-id> run shows replan_invalidated entries that
postdate the task's first journal entry.

Test asserts:
  - a task with journal entries BEFORE a replan → trace includes the replan event
  - a task with journal entries AFTER a replan → trace does NOT include it (predates)
  - a task with no journal entries → trace does not crash; replan not shown
  - --json output includes the replan event in the events list
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()

_SHA256_ZERO = "sha256:" + "0" * 64


def _invoke_trace(tmp_path: Path, task_id: str, *, json_out: bool = True) -> Any:
    args = (["--json"] if json_out else []) + ["trace", task_id]
    with unittest.mock.patch("sdlc.cli.trace.get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _append_journal_entry(
    tmp_path: Path,
    *,
    seq: int,
    ts: str,
    kind: str,
    target_id: str,
    actor: str = "test",
    payload: dict | None = None,
    after_hash: str = _SHA256_ZERO,
) -> None:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entry = JournalEntry(
        monotonic_seq=seq,
        ts=ts,
        kind=kind,
        actor=actor,
        target_id=target_id,
        before_hash=None,
        after_hash=after_hash,
        payload=payload or {},
    )
    append_sync(entry, journal_path=journal_path)


# ---------------------------------------------------------------------------
# AC6/D1 — trace surfaces replan_invalidated that postdates the task
# ---------------------------------------------------------------------------


def test_trace_includes_replan_event_postdating_task(tmp_path: Path) -> None:
    """Task entry at T1, replan event at T2 (T2 > T1) → trace shows replan."""
    _init_repo(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"

    # Task journal entry at earlier time
    _append_journal_entry(
        tmp_path,
        seq=1,
        ts="2026-05-19T09:00:00.000Z",
        kind="agent_dispatch",
        target_id=task_id,
        payload={"task_id": task_id},
    )

    # replan_invalidated entry at later time
    _append_journal_entry(
        tmp_path,
        seq=2,
        ts="2026-05-19T10:00:00.000Z",
        kind="replan_invalidated",
        target_id="02-Architecture/02-System/ARCHITECTURE.md",
        payload={"scope": "02-Architecture/02-System/ARCHITECTURE.md", "scope_phase": 2},
    )

    r = _invoke_trace(tmp_path, task_id)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    kinds = [e["kind"] for e in data["events"]]
    assert "replan_invalidated" in kinds


def test_trace_excludes_replan_event_predating_task(tmp_path: Path) -> None:
    """replan event at T1, task entry at T2 (T2 > T1) → trace DOES NOT show replan."""
    _init_repo(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"

    # replan_invalidated entry at earlier time
    _append_journal_entry(
        tmp_path,
        seq=1,
        ts="2026-05-19T08:00:00.000Z",
        kind="replan_invalidated",
        target_id="02-Architecture/02-System/ARCHITECTURE.md",
        payload={"scope": "02-Architecture/02-System/ARCHITECTURE.md", "scope_phase": 2},
    )

    # Task entry at later time
    _append_journal_entry(
        tmp_path,
        seq=2,
        ts="2026-05-19T10:00:00.000Z",
        kind="agent_dispatch",
        target_id=task_id,
        payload={"task_id": task_id},
    )

    r = _invoke_trace(tmp_path, task_id)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    kinds = [e["kind"] for e in data["events"]]
    assert "replan_invalidated" not in kinds


def test_trace_no_task_entries_no_replan_shown(tmp_path: Path) -> None:
    """Task has no journal entries → replan event not shown (nothing to postdate)."""
    _init_repo(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"

    # Only a replan entry, no task entry
    _append_journal_entry(
        tmp_path,
        seq=1,
        ts="2026-05-19T09:00:00.000Z",
        kind="replan_invalidated",
        target_id="02-Architecture/02-System/ARCHITECTURE.md",
        payload={"scope": "02-Architecture/02-System/ARCHITECTURE.md", "scope_phase": 2},
    )

    r = _invoke_trace(tmp_path, task_id)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["event_count"] == 0


def test_trace_multiple_replans_shows_all_postdating(tmp_path: Path) -> None:
    """Multiple replan events — only those postdating the task are shown."""
    _init_repo(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"

    # Early replan (before task)
    _append_journal_entry(
        tmp_path,
        seq=1,
        ts="2026-05-19T08:00:00.000Z",
        kind="replan_invalidated",
        target_id="01-Requirement/PRODUCT.md",
        payload={"scope": "01-Requirement/PRODUCT.md", "scope_phase": 1},
    )

    # Task entry
    _append_journal_entry(
        tmp_path,
        seq=2,
        ts="2026-05-19T09:00:00.000Z",
        kind="agent_dispatch",
        target_id=task_id,
        payload={"task_id": task_id},
    )

    # Late replan (after task)
    _append_journal_entry(
        tmp_path,
        seq=3,
        ts="2026-05-19T10:00:00.000Z",
        kind="replan_invalidated",
        target_id="02-Architecture/02-System/ARCHITECTURE.md",
        payload={"scope": "02-Architecture/02-System/ARCHITECTURE.md", "scope_phase": 2},
    )

    r = _invoke_trace(tmp_path, task_id)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    replan_events = [e for e in data["events"] if e["kind"] == "replan_invalidated"]
    # Only the late replan should appear
    assert len(replan_events) == 1
    assert replan_events[0]["target_id"] == "02-Architecture/02-System/ARCHITECTURE.md"

"""`sdlc trace <task-id>` implementation (FR33, NFR-OBS-3, Architecture §803, §1159).

Filters journal + agent_runs by task-id; chronological merge.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Final

import typer

from sdlc.cli._agent_runs import iter_agent_runs as _iter_agent_runs
from sdlc.cli._event_builders import (
    agent_event_from_record as _agent_event_from_record,
)
from sdlc.cli._event_builders import (
    journal_event_from_entry as _journal_event_from_entry,
)
from sdlc.cli._paths import get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import IdsError, JournalError
from sdlc.ids import parse_task_id

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_AGENT_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_AGENT_RUN_DISPLAY_FIELDS: Final[tuple[str, ...]] = (
    "ts",
    "agent",
    "target_id",
    "stage",
    "outcome",
    "duration_ms",
)


def _event_affects_task(entry: JournalEntry, task_id: str) -> bool:
    """Return True if this journal entry pertains to the given task-id.

    Three predicates per AC1.5:
      1. entry.target_id == task_id (direct mutation/scan/etc.)
      2. entry.kind == "agent_dispatch" and entry.payload.get("task_id") == task_id
      3. entry.kind == "hook_invocation" and entry.payload.get("target_id") == task_id
    """
    if entry.target_id == task_id:
        return True
    if entry.kind == "agent_dispatch":
        payload_task_id = entry.payload.get("task_id")
        if isinstance(payload_task_id, str) and payload_task_id == task_id:
            return True
    if entry.kind == "hook_invocation":
        payload_target = entry.payload.get("target_id")
        if isinstance(payload_target, str) and payload_target == task_id:
            return True
    return False


def _record_matches_task(record: dict[str, Any], task_id: str) -> bool:
    for key in ("target_id", "task_id"):
        v = record.get(key)
        if isinstance(v, str) and v == task_id:
            return True
    return False


def _collect_events(
    *,
    journal_path: Path,
    agent_runs_path: Path,
    task_id: str,
) -> list[dict[str, Any]]:
    from sdlc.journal import iter_entries  # deferred per Architecture §488

    events: list[dict[str, Any]] = []
    for entry in iter_entries(journal_path):
        if not _event_affects_task(entry, task_id):
            continue
        event = _journal_event_from_entry(entry)
        if event is not None:
            events.append(event)
    for record in _iter_agent_runs(agent_runs_path):
        if not _record_matches_task(record, task_id):
            continue
        event = _agent_event_from_record(record)
        if event is not None:
            events.append(event)
    events.sort(
        key=lambda e: (
            e["_sort_ts"],
            0 if e["source"] == "journal" else 1,
            e["_sort_seq"],
        )
    )
    for e in events:
        e.pop("_sort_ts", None)
        e.pop("_sort_seq", None)
    return events


def _load_events(
    *,
    ctx: typer.Context,
    journal_path: Path,
    agent_runs_path: Path,
    task_id: str,
) -> list[dict[str, Any]]:
    """Collect + merge events; emit_error on failure (raises typer.Exit)."""
    try:
        return _collect_events(
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            task_id=task_id,
        )
    except JournalError as exc:
        emit_error(
            "ERR_JOURNAL_READ_FAILED",
            f"journal read failed: {exc.message}",
            ctx=ctx,
            details=dict(exc.details),
        )
    except OSError as exc:
        emit_error(
            "ERR_AGENT_RUNS_READ_FAILED",
            f"agent_runs read failed: {exc}",
            ctx=ctx,
            details={"path": str(agent_runs_path)},
        )
    # emit_error is NoReturn; defensive fallback if a test stub or future
    # refactor breaks that contract — keeps the typed return non-None.
    raise AssertionError("unreachable: emit_error did not exit")


def _format_event_line(e: dict[str, Any]) -> str:
    if e["source"] == "journal":
        return f"  [{e['ts']}]   kind={e['kind']:<20} target={e['target_id']}   actor={e['actor']}"
    fields = "   ".join(
        f"{name}={e.get(name)}" for name in _AGENT_RUN_DISPLAY_FIELDS if name != "ts"
    )
    return f"  [{e['ts']}]   agent_run             {fields}"


def run_trace(*, ctx: typer.Context, task_id: str) -> None:
    """Reconstruct chronological history of all events affecting task_id."""
    root = get_repo_root_or_cwd()
    if not (root / _STATE_PATH_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    try:
        parse_task_id(task_id)
    except IdsError as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"invalid task identifier: {exc.message}",
            ctx=ctx,
            details=dict(exc.details),
        )

    events = _load_events(
        ctx=ctx,
        journal_path=root / _JOURNAL_PATH_REL,
        agent_runs_path=root / _AGENT_RUNS_PATH_REL,
        task_id=task_id,
    )

    if ctx.obj.get("json", False):
        emit_json(
            "trace",
            {
                "task_id": task_id,
                "project_root": str(root),
                "events": events,
                "event_count": len(events),
            },
            ctx=ctx,
        )
        return

    echo(f"sdlc trace {task_id} — {len(events)} events", ctx=ctx)
    if not events:
        echo("(no events recorded for this task yet)", ctx=ctx)
        return
    for e in events:
        echo(_format_event_line(e), ctx=ctx)

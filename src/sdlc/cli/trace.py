"""`sdlc trace <task-id>` implementation (FR33, NFR-OBS-3, Architecture §803, §1159).

Filters journal + agent_runs by task-id; chronological merge.
AC6/D1 (Story 2A.19): `replan_invalidated` is a global event — any trace invocation
surfaces `kind="replan_invalidated"` entries that postdate the traced task's
first journal entry (global-event passthrough rule).
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
from sdlc.cli.output import emit_error, emit_json, make_console
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


_GLOBAL_EVENT_KINDS: frozenset[str] = frozenset({"replan_invalidated"})


def _add_postdating_globals(
    task_events: list[dict[str, Any]],
    global_candidates: list[dict[str, Any]],
) -> None:
    """AC6/D1: append global events that postdate the task's earliest journal entry.

    Mutates task_events in-place; no-op when either list is empty.
    """
    if not task_events or not global_candidates:
        return
    earliest_task_ts = min(e["_sort_ts"] for e in task_events)
    for ge in global_candidates:
        if ge["_sort_ts"] >= earliest_task_ts:
            task_events.append(ge)


def _partition_journal(
    journal_path: Path,
    task_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split journal into (task_events, global_candidates)."""
    from sdlc.journal import iter_entries  # deferred per Architecture §488

    task_events: list[dict[str, Any]] = []
    global_candidates: list[dict[str, Any]] = []
    for entry in iter_entries(journal_path):
        if entry.kind in _GLOBAL_EVENT_KINDS:
            event = _journal_event_from_entry(entry)
            if event is not None:
                global_candidates.append(event)
            continue
        if not _event_affects_task(entry, task_id):
            continue
        event = _journal_event_from_entry(entry)
        if event is not None:
            task_events.append(event)
    return task_events, global_candidates


def _collect_agent_run_events(
    agent_runs_path: Path,
    task_id: str,
) -> list[dict[str, Any]]:
    """Return agent_run events matching task_id."""
    events: list[dict[str, Any]] = []
    for record in _iter_agent_runs(agent_runs_path):
        if not _record_matches_task(record, task_id):
            continue
        event = _agent_event_from_record(record)
        if event is not None:
            events.append(event)
    return events


def _collect_events(
    *,
    journal_path: Path,
    agent_runs_path: Path,
    task_id: str,
) -> list[dict[str, Any]]:
    task_events, global_candidates = _partition_journal(journal_path, task_id)
    task_events.extend(_collect_agent_run_events(agent_runs_path, task_id))
    _add_postdating_globals(task_events, global_candidates)
    task_events.sort(
        key=lambda e: (
            e["_sort_ts"],
            0 if e["source"] == "journal" else 1,
            e["_sort_seq"],
        )
    )
    for e in task_events:
        e.pop("_sort_ts", None)
        e.pop("_sort_seq", None)
    return task_events


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


def _format_event_line_rich(e: dict[str, Any]) -> str:
    """Return a Rich markup string for one trace event."""
    ts = e["ts"]
    if e["source"] == "journal":
        kind = e["kind"]
        target = e.get("target_id", "?")
        actor = e.get("actor", "?")
        before_h = e.get("before_hash") or "—"
        after_h = e.get("after_hash") or "—"
        return (
            f"  [dim]{ts}[/dim]   [bold]{kind:<20}[/bold]"
            f" target={target}   actor={actor}\n"
            f"  [dim]  before={before_h}  after={after_h}[/dim]"
        )
    fields = "   ".join(
        f"{name}={e.get(name)}" for name in _AGENT_RUN_DISPLAY_FIELDS if name != "ts"
    )
    return f"  [dim]{ts}[/dim]   [bold]agent_run[/bold]             {fields}"


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

    console = make_console(ctx)
    console.print(f"sdlc trace {task_id} — {len(events)} events")
    if not events:
        console.print("(no events recorded for this task yet)")
        return
    for e in events:
        console.print(_format_event_line_rich(e))

"""`sdlc logs` — tail journal + agent_runs with filters + follow-mode (FR45, NFR-OBS-6).

--follow --json emits NDJSON (one object per line); see ADR-021.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import time
from pathlib import Path
from typing import Any, Final

import typer

from sdlc.cli._agent_runs import iter_agent_runs as _iter_agent_runs
from sdlc.cli._paths import get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import IdsError, JournalError
from sdlc.ids import parse_task_id

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_AGENT_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_FOLLOW_INTERVAL_S: Final[float] = 0.25


def _parse_ts(ts: str) -> datetime.datetime:
    """RFC 3339 UTC string → datetime. 3.10-compatible."""
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _journal_actor_matches_agent(actor: str, agent_name: str) -> bool:
    return actor == f"agent:{agent_name}"  # kept for now; see ADR-021


def _journal_entry_matches_filters(
    entry: JournalEntry,
    filter_task: str | None,
    filter_agent: str | None,
) -> bool:
    if filter_task is not None:
        matches_task = (
            entry.target_id == filter_task
            or (
                entry.kind == "agent_dispatch"
                and isinstance(entry.payload.get("task_id"), str)
                and entry.payload.get("task_id") == filter_task
            )
            or (
                entry.kind == "hook_invocation"
                and isinstance(entry.payload.get("target_id"), str)
                and entry.payload.get("target_id") == filter_task
            )
        )
        if not matches_task:
            return False
    return filter_agent is None or (
        _journal_actor_matches_agent(entry.actor, filter_agent)
        or entry.payload.get("agent") == filter_agent
    )


def _agent_run_record_matches_filters(
    record: dict[str, Any],
    filter_task: str | None,
    filter_agent: str | None,
) -> bool:
    if filter_task is not None:
        record_task = record.get("target_id") or record.get("task_id")
        if not (isinstance(record_task, str) and record_task == filter_task):
            return False
    return filter_agent is None or record.get("agent") == filter_agent


def _collect_logs(
    *,
    journal_path: Path,
    agent_runs_path: Path,
    filter_task: str | None,
    filter_agent: str | None,
) -> list[dict[str, Any]]:
    from sdlc.journal import iter_entries  # deferred

    events: list[dict[str, Any]] = []
    for entry in iter_entries(journal_path):
        if not _journal_entry_matches_filters(entry, filter_task, filter_agent):
            continue
        events.append(
            {
                "source": "journal",
                "ts": entry.ts,
                "_sort_ts": _parse_ts(entry.ts),
                "_sort_seq": entry.monotonic_seq,
                "monotonic_seq": entry.monotonic_seq,
                "kind": entry.kind,
                "actor": entry.actor,
                "target_id": entry.target_id,
                "before_hash": entry.before_hash,
                "after_hash": entry.after_hash,
                "payload": dict(entry.payload),
            }
        )
    for record in _iter_agent_runs(agent_runs_path):
        if not _agent_run_record_matches_filters(record, filter_task, filter_agent):
            continue
        ts = record.get("ts")
        if not isinstance(ts, str):
            continue
        events.append(
            {
                "source": "agent_runs",
                "ts": ts,
                "_sort_ts": _parse_ts(ts),
                "_sort_seq": -1,
                "agent": record.get("agent"),
                "stage": record.get("stage"),
                "outcome": record.get("outcome"),
                "duration_ms": record.get("duration_ms"),
                "target_id": record.get("target_id") or record.get("task_id"),
                "raw": record,
            }
        )
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


def _format_log_line_human(event: dict[str, Any]) -> str:
    if event["source"] == "journal":
        return (
            f"{event['ts']}  [journal/{event['kind']}]   "
            f"actor={event['actor']:<10}   target={event['target_id']}"
        )
    return (
        f"{event['ts']}  [agent_run/{event.get('agent', '?')}]   "
        f"stage={event.get('stage', '?')}   outcome={event.get('outcome', '?')}   "
        f"task={event.get('target_id', '?')}"
    )


def _emit_event(event: dict[str, Any], *, json_mode: bool, ctx: typer.Context) -> None:
    """Emit one event — JSON line in json_mode; formatted text otherwise."""
    if json_mode:
        typer.echo(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    else:
        echo(_format_log_line_human(event), ctx=ctx)


def _poll_journal(
    journal_path: Path,
    journal_pos: int,
    filter_task: str | None,
    filter_agent: str | None,
    *,
    json_mode: bool,
    ctx: typer.Context,
) -> int:
    """Poll journal for new lines; return updated file position."""
    if not journal_path.exists():
        return journal_pos
    new_size = journal_path.stat().st_size
    if new_size <= journal_pos:
        return journal_pos
    with journal_path.open("r", encoding="utf-8") as fh:
        fh.seek(journal_pos)
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = JournalEntry.model_validate_json(stripped)
            except (ValueError, TypeError) as exc:
                _logger.warning("follow: malformed journal line — skipping: %s", exc)
                continue
            if not _journal_entry_matches_filters(entry, filter_task, filter_agent):
                continue
            event: dict[str, Any] = {
                "source": "journal",
                "ts": entry.ts,
                "kind": entry.kind,
                "actor": entry.actor,
                "target_id": entry.target_id,
                "monotonic_seq": entry.monotonic_seq,
            }
            _emit_event(event, json_mode=json_mode, ctx=ctx)
    return new_size


def _poll_agent_runs(
    agent_runs_path: Path,
    agent_pos: int,
    filter_task: str | None,
    filter_agent: str | None,
    *,
    json_mode: bool,
    ctx: typer.Context,
) -> int:
    """Poll agent_runs.jsonl for new lines; return updated file position."""
    if not agent_runs_path.exists():
        return agent_pos
    new_size = agent_runs_path.stat().st_size
    if new_size <= agent_pos:
        return agent_pos
    with agent_runs_path.open("r", encoding="utf-8") as fh:
        fh.seek(agent_pos)
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw: object = json.loads(stripped)
            except json.JSONDecodeError as exc:
                _logger.warning("follow: malformed agent_runs line — skipping: %s", exc)
                continue
            if not isinstance(raw, dict):
                continue
            record: dict[str, Any] = raw
            if not _agent_run_record_matches_filters(record, filter_task, filter_agent):
                continue
            ar_event: dict[str, Any] = {
                "source": "agent_runs",
                "ts": record.get("ts", "?"),
                "agent": record.get("agent"),
                "stage": record.get("stage"),
                "outcome": record.get("outcome"),
                "duration_ms": record.get("duration_ms"),
                "target_id": record.get("target_id") or record.get("task_id"),
            }
            _emit_event(ar_event, json_mode=json_mode, ctx=ctx)
    return new_size


def _follow_streams(
    journal_path: Path,
    agent_runs_path: Path,
    filter_task: str | None,
    filter_agent: str | None,
    ctx: typer.Context,
) -> None:
    """Tail-follow journal + agent_runs. Polls at _FOLLOW_INTERVAL_S until KI."""
    journal_pos = journal_path.stat().st_size if journal_path.exists() else 0
    agent_pos = agent_runs_path.stat().st_size if agent_runs_path.exists() else 0
    json_mode = bool(ctx.obj.get("json", False))
    with contextlib.suppress(KeyboardInterrupt):
        while True:
            journal_pos = _poll_journal(
                journal_path,
                journal_pos,
                filter_task,
                filter_agent,
                json_mode=json_mode,
                ctx=ctx,
            )
            agent_pos = _poll_agent_runs(
                agent_runs_path,
                agent_pos,
                filter_task,
                filter_agent,
                json_mode=json_mode,
                ctx=ctx,
            )
            time.sleep(_FOLLOW_INTERVAL_S)


def _load_events_or_error(
    *,
    ctx: typer.Context,
    journal_path: Path,
    agent_runs_path: Path,
    filter_task: str | None,
    filter_agent: str | None,
) -> list[dict[str, Any]]:
    """Collect events; emit_error on JournalError / OSError."""
    try:
        return _collect_logs(
            journal_path=journal_path,
            agent_runs_path=agent_runs_path,
            filter_task=filter_task,
            filter_agent=filter_agent,
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


def run_logs(
    *,
    ctx: typer.Context,
    filter_task: str | None,
    filter_agent: str | None,
    follow: bool,
) -> None:
    """Tail journal + agent_runs.jsonl with optional filters and follow-mode."""
    root = get_repo_root_or_cwd()
    if not (root / _STATE_PATH_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    if filter_task is not None:
        try:
            parse_task_id(filter_task)
        except IdsError as exc:
            emit_error(
                "ERR_USER_INPUT",
                f"invalid task identifier in --filter-task: {exc.message}",
                ctx=ctx,
                details=dict(exc.details),
            )

    journal_path = root / _JOURNAL_PATH_REL
    agent_runs_path = root / _AGENT_RUNS_PATH_REL

    events = _load_events_or_error(
        ctx=ctx,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        filter_task=filter_task,
        filter_agent=filter_agent,
    )

    json_mode = bool(ctx.obj.get("json", False))

    if json_mode and not follow:
        emit_json(
            "logs",
            {
                "filters": {"task_id": filter_task, "agent": filter_agent},
                "events": events,
                "event_count": len(events),
            },
            ctx=ctx,
        )
        return

    for e in events:
        _emit_event(e, json_mode=json_mode, ctx=ctx)

    if not follow:
        return

    _follow_streams(
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        filter_task=filter_task,
        filter_agent=filter_agent,
        ctx=ctx,
    )
    raise typer.Exit(code=0)

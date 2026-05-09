"""`sdlc logs` — tail journal + agent_runs with filters + follow-mode (FR45, NFR-OBS-6).

--follow --json emits NDJSON (one object per line); see ADR-021.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import typer

from sdlc.cli._logs_filter import (
    _agent_run_record_matches_filters,
    _collect_logs,
    _journal_entry_matches_filters,
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
_FOLLOW_INTERVAL_S: Final[float] = 0.25
_ACTOR_COLUMN_WIDTH: Final[int] = 10
_LOGS_NDJSON_COMMAND: Final[str] = "logs"
_OUTCOME_STYLES: Final[Mapping[str, str]] = MappingProxyType(
    {"success": "green", "failure": "red", "partial": "yellow"}
)


def _format_log_line_rich(event: dict[str, Any]) -> str:
    """Return a Rich markup string for one log event."""
    ts = event["ts"]
    if event["source"] == "journal":
        kind = event["kind"]
        actor = event.get("actor", "?")
        target = event.get("target_id", "?")
        return (
            f"[dim]{ts}[/dim]  [bold]\\[journal/{kind}][/bold]   "
            f"actor={actor:<{_ACTOR_COLUMN_WIDTH}}   target={target}"
        )
    agent = event.get("agent", "?")
    stage = event.get("stage", "?")
    outcome = str(event.get("outcome", "?"))
    task = event.get("target_id", "?")
    outcome_style = _OUTCOME_STYLES.get(outcome, "")
    outcome_str = (
        f"[{outcome_style}]outcome={outcome}[/{outcome_style}]"
        if outcome_style
        else f"outcome={outcome}"
    )
    return (
        f"[dim]{ts}[/dim]  [bold]\\[agent_run/{agent}][/bold]   "
        f"stage={stage}   {outcome_str}   task={task}"
    )


def _emit_event(event: dict[str, Any], *, json_mode: bool, ctx: typer.Context) -> None:
    """Emit one event — JSON line in json_mode; formatted text otherwise.

    NDJSON lines carry a `command` field so consumers see one consistent shape
    across the historical→live transition under `--follow --json` (see ADR-021).
    Human-readable output uses rich markup for styling (AC5 / ADR-021 D3).
    """
    if json_mode:
        line_payload = dict(event)
        line_payload.setdefault("command", _LOGS_NDJSON_COMMAND)
        typer.echo(
            json.dumps(line_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        )
    else:
        make_console(ctx).print(_format_log_line_rich(event))


_NO_INODE: Final[int] = -1  # sentinel: no previous inode tracked


def _poll_journal(  # noqa: C901
    journal_path: Path,
    journal_pos: int,
    filter_task: str | None,
    filter_agent: str | None,
    *,
    json_mode: bool,
    ctx: typer.Context,
    inode: int = _NO_INODE,
) -> tuple[int, int]:
    """Poll journal for new lines; return (new_inode, new_pos).

    Detects rotation (inode change) and truncation (size < pos): on either,
    resets pos to 0 and warns so follow-mode doesn't miss rotated content.
    """
    if not journal_path.exists():
        return inode, journal_pos
    stat = journal_path.stat()
    new_inode = stat.st_ino
    new_size = stat.st_size

    # Rotation: inode replaced (logrotate / rename+new file).
    if inode not in (_NO_INODE, new_inode):
        _logger.warning(
            "follow: journal rotated (inode %d → %d) — resetting position",
            inode,
            new_inode,
        )
        journal_pos = 0

    # Truncation: file shrank below last known position.
    if new_size < journal_pos:
        _logger.warning(
            "follow: journal truncated (pos %d > size %d) — resetting position",
            journal_pos,
            new_size,
        )
        journal_pos = 0

    if new_size <= journal_pos:
        return new_inode, journal_pos
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
                "monotonic_seq": entry.monotonic_seq,
                "kind": entry.kind,
                "actor": entry.actor,
                "target_id": entry.target_id,
                "before_hash": entry.before_hash,
                "after_hash": entry.after_hash,
                "payload": dict(entry.payload),
            }
            _emit_event(event, json_mode=json_mode, ctx=ctx)
    return new_inode, new_size


def _poll_agent_runs(  # noqa: C901
    agent_runs_path: Path,
    agent_pos: int,
    filter_task: str | None,
    filter_agent: str | None,
    *,
    json_mode: bool,
    ctx: typer.Context,
    inode: int = _NO_INODE,
) -> tuple[int, int]:
    """Poll agent_runs.jsonl for new lines; return (new_inode, new_pos).

    Detects rotation and truncation the same way as _poll_journal.
    """
    if not agent_runs_path.exists():
        return inode, agent_pos
    stat = agent_runs_path.stat()
    new_inode = stat.st_ino
    new_size = stat.st_size

    if inode not in (_NO_INODE, new_inode):
        _logger.warning(
            "follow: agent_runs rotated (inode %d → %d) — resetting position",
            inode,
            new_inode,
        )
        agent_pos = 0

    if new_size < agent_pos:
        _logger.warning(
            "follow: agent_runs truncated (pos %d > size %d) — resetting position",
            agent_pos,
            new_size,
        )
        agent_pos = 0

    if new_size <= agent_pos:
        return new_inode, agent_pos
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
    return new_inode, new_size


def _follow_streams(
    journal_path: Path,
    agent_runs_path: Path,
    filter_task: str | None,
    filter_agent: str | None,
    ctx: typer.Context,
    *,
    journal_pos: int,
    agent_pos: int,
    _stop: threading.Event | None = None,
) -> None:
    """Tail-follow journal + agent_runs. Polls at _FOLLOW_INTERVAL_S until KI.

    Caller must pass the file sizes captured BEFORE the historical pass so
    events appended in the gap between historical-collect and follow-start
    are not skipped (race window). BrokenPipeError is suppressed to avoid
    a Python traceback when stdout is piped to a process that exits early
    (e.g. `sdlc logs --follow | head -5`).

    Tracks (inode, pos) per file so rotation and truncation are detected.
    _stop is a test seam: set it to break the loop without KeyboardInterrupt.
    """
    json_mode = bool(ctx.obj.get("json", False))
    journal_inode = _NO_INODE
    agent_inode = _NO_INODE
    with contextlib.suppress(KeyboardInterrupt, BrokenPipeError):
        while True:
            if _stop is not None and _stop.is_set():
                break
            journal_inode, journal_pos = _poll_journal(
                journal_path,
                journal_pos,
                filter_task,
                filter_agent,
                json_mode=json_mode,
                ctx=ctx,
                inode=journal_inode,
            )
            agent_inode, agent_pos = _poll_agent_runs(
                agent_runs_path,
                agent_pos,
                filter_task,
                filter_agent,
                json_mode=json_mode,
                ctx=ctx,
                inode=agent_inode,
            )
            time.sleep(_FOLLOW_INTERVAL_S)


def run_logs(  # noqa: C901
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

    if filter_agent is not None and not filter_agent.strip():
        emit_error(
            "ERR_USER_INPUT",
            "--filter-agent must not be empty",
            ctx=ctx,
            details={"input": filter_agent, "rule": "non_empty"},
        )

    journal_path = root / _JOURNAL_PATH_REL
    agent_runs_path = root / _AGENT_RUNS_PATH_REL

    # Capture file sizes BEFORE the historical pass so events appended in the
    # gap between historical-collect and follow-start are not skipped.
    journal_pos_before = journal_path.stat().st_size if journal_path.exists() else 0
    agent_pos_before = agent_runs_path.stat().st_size if agent_runs_path.exists() else 0

    try:
        events = _collect_logs(
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
        journal_pos=journal_pos_before,
        agent_pos=agent_pos_before,
    )
    raise typer.Exit(code=0)

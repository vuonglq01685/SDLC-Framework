"""Filter predicates and log-collection helper for sdlc logs (factored out of logs.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sdlc.cli._agent_runs import iter_agent_runs as _iter_agent_runs
from sdlc.cli._event_builders import (
    agent_event_from_record as _agent_event_from_record,
)
from sdlc.cli._event_builders import (
    journal_event_from_entry as _journal_event_from_entry,
)
from sdlc.contracts.journal_entry import JournalEntry


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
        event = _journal_event_from_entry(entry)
        if event is not None:
            events.append(event)
    for record in _iter_agent_runs(agent_runs_path):
        if not _agent_run_record_matches_filters(record, filter_task, filter_agent):
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

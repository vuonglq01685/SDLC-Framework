"""Shared event-builder helpers for cli/trace.py and cli/logs.py.

Keeps the journal/agent_run event-dict shape, the `ts` parsing posture,
and the malformed-record skip policy in one place — eliminates the
parallel-but-divergent helpers flagged by the 2026-05-09 review.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sdlc.contracts.journal_entry import JournalEntry

_logger = logging.getLogger(__name__)


def parse_ts(ts: str) -> datetime.datetime:
    """RFC 3339 UTC string → datetime. 3.10-compatible.

    Naive datetimes (no offset, no Z) are coerced to UTC so the merge sort
    never mixes offset-aware and offset-naive values (TypeError on compare).
    """
    normalized = ts.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def safe_parse_ts(ts: str, *, source: str) -> datetime.datetime | None:
    """Wrap parse_ts: log + return None on malformed input instead of crashing.

    Mirrors `journal/reader.py`'s permissive-reader posture: a single bad
    timestamp must not tank the whole `trace` / `logs` invocation.
    """
    try:
        return parse_ts(ts)
    except ValueError as exc:
        _logger.warning(
            "malformed ts in %s record: %r — skipping event: %s",
            source,
            ts,
            exc,
        )
        return None


def journal_event_from_entry(entry: JournalEntry) -> dict[str, Any] | None:
    """Build a sortable journal event dict; None if `ts` is malformed."""
    sort_ts = safe_parse_ts(entry.ts, source="journal")
    if sort_ts is None:
        return None
    return {
        "source": "journal",
        "ts": entry.ts,
        "_sort_ts": sort_ts,
        "_sort_seq": entry.monotonic_seq,
        "monotonic_seq": entry.monotonic_seq,
        "kind": entry.kind,
        "actor": entry.actor,
        "target_id": entry.target_id,
        "before_hash": entry.before_hash,
        "after_hash": entry.after_hash,
        "payload": dict(entry.payload),
    }


def agent_event_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Build a sortable agent_run event dict; None if `ts` missing or malformed."""
    ts = record.get("ts")
    if not isinstance(ts, str):
        _logger.warning(
            "agent_runs record missing string `ts` (got %s) — skipping: %r",
            type(ts).__name__,
            record,
        )
        return None
    sort_ts = safe_parse_ts(ts, source="agent_runs")
    if sort_ts is None:
        return None
    return {
        "source": "agent_runs",
        "ts": ts,
        "_sort_ts": sort_ts,
        "_sort_seq": -1,
        "agent": record.get("agent"),
        "stage": record.get("stage"),
        "outcome": record.get("outcome"),
        "duration_ms": record.get("duration_ms"),
        "target_id": record.get("target_id") or record.get("task_id"),
        "raw": dict(record),
    }

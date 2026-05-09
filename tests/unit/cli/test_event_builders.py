"""Unit tests for sdlc.cli._event_builders (Story 1.18.1, AC2).

B-P4: mixed naive + aware ts sorts without TypeError.
B-P5: malformed ts warns and skips event.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def test_parse_ts_naive_coerced_to_utc() -> None:
    """B-P4 (part): naive ts (no Z/offset) is treated as UTC, not left naive."""
    from sdlc.cli._event_builders import parse_ts

    naive_dt = parse_ts("2026-01-01T00:00:00")
    aware_dt = parse_ts("2026-01-01T00:00:00Z")
    # Both must be comparable (no TypeError) and equal.
    assert naive_dt == aware_dt
    assert naive_dt.tzinfo is not None


def test_parse_ts_mixed_awareness_sorts_chronologically() -> None:
    """B-P4: naive and aware ts values sort chronologically without TypeError."""
    from sdlc.cli._event_builders import parse_ts

    ts_naive = parse_ts("2026-01-01T00:00:01")
    ts_aware_early = parse_ts("2026-01-01T00:00:00Z")
    ts_aware_late = parse_ts("2026-01-01T00:00:02Z")

    # Should be sortable without TypeError.
    sorted_dts = sorted([ts_aware_late, ts_naive, ts_aware_early])
    assert sorted_dts == [ts_aware_early, ts_naive, ts_aware_late]


def test_safe_parse_ts_malformed_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """B-P5: malformed ts → safe_parse_ts returns None and logs a WARNING; no exception."""
    from sdlc.cli._event_builders import safe_parse_ts

    with caplog.at_level(logging.WARNING):
        result = safe_parse_ts("NOT-A-DATE", source="journal")

    assert result is None
    assert "malformed ts" in caplog.text.lower()


def test_safe_parse_ts_valid_returns_datetime() -> None:
    """safe_parse_ts returns a datetime for a valid RFC 3339 string."""
    import datetime

    from sdlc.cli._event_builders import safe_parse_ts

    dt = safe_parse_ts("2026-01-01T00:00:00Z", source="journal")
    assert dt is not None
    assert isinstance(dt, datetime.datetime)
    assert dt.tzinfo is not None


def test_journal_event_from_entry_malformed_ts_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """B-P5 (journal path): JournalEntry with bad ts yields None from journal_event_from_entry.

    model_construct bypasses Pydantic validation so we can inject a malformed ts
    (simulates a schema migration that introduces a looser ts format in the future).
    """
    from sdlc.cli._event_builders import journal_event_from_entry
    from sdlc.contracts.journal_entry import JournalEntry

    entry = JournalEntry.model_construct(
        schema_version=1,
        monotonic_seq=0,
        ts="NOT-A-DATE",
        actor="cli",
        kind="scan_completed",
        target_id="state",
        before_hash=None,
        after_hash="sha256:" + "1" * 64,
        payload={},
    )
    with caplog.at_level(logging.WARNING):
        result = journal_event_from_entry(entry)
    assert result is None
    assert "malformed ts" in caplog.text.lower()


def test_agent_event_from_record_malformed_ts_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """B-P5 (agent_runs path): record with bad ts yields None from agent_event_from_record."""
    from sdlc.cli._event_builders import agent_event_from_record

    record = {"ts": "GARBAGE", "agent": "impl", "target_id": "EPIC-x-S01-y-T01-z"}
    with caplog.at_level(logging.WARNING):
        result = agent_event_from_record(record)
    assert result is None
    assert "malformed ts" in caplog.text.lower()

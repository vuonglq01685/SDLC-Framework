"""Highest-monotonic-seq scanner extracted from journal/writer.py (ADR-014 D1).

Caller MUST hold the write flock — concurrent appenders both reading the same highest
value and both succeeding is the failure mode the lock prevents.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError

_logger = logging.getLogger(__name__)


def _read_highest_seq(journal_path: Path) -> int:
    """Return the maximum ``monotonic_seq`` across all parseable entries, or ``-1`` if empty.

    Caller must hold the write lock. Malformed lines are skipped with a logged warning —
    the writer's ``validate_seq`` check is best-effort robustness; the property test asserts
    all written entries are well-formed.

    Re-raises ``OSError`` as ``JournalError(step="read_highest_seq")`` so the caller never
    silently accepts a duplicate seq because the file became unreadable mid-flight
    (Story 1.11 review patch — Blind H3 + Edge H4 implication).
    """
    if not journal_path.exists():
        return -1
    highest = -1
    try:
        with journal_path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = JournalEntry.model_validate_json(stripped)
                    highest = max(highest, entry.monotonic_seq)
                except (ValueError, TypeError) as e:
                    _logger.warning(
                        "malformed journal line at %s:%d: %s — skipping",
                        journal_path,
                        lineno,
                        e,
                    )
    except OSError as e:
        raise JournalError(
            f"journal read failed during seq scan: {e}",
            details={
                "path": str(journal_path),
                "errno": e.errno,
                "step": "read_highest_seq",
            },
        ) from e
    return highest

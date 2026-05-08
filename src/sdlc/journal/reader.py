"""POSIX-cross-platform journal reader: pure read, no flock required (Architecture §522, §1060).

Reads sort strictly by monotonic_seq; order in file IS the order returned (O_APPEND guarantees).

Trade-off: malformed lines are skipped with a logged warning (permissive reader) to support
Story 1.20's sdlc rebuild-state recovery path. Mitigation: JournalError(step="reader_invariant")
fires if seqs go out-of-order — the dangerous corruption case is still caught loudly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError

_logger = logging.getLogger(__name__)


def iter_entries(journal_path: Path) -> Iterator[JournalEntry]:
    """Yield JournalEntry records in file order (= monotonic_seq order by O_APPEND invariant).

    File order IS monotonic_seq order because the writer's validate_seq enforces strictly
    increasing seqs under flock. A second-line-of-defence assertion raises JournalError if
    a seq regression is detected — protecting downstream projection (Story 1.12) from
    silently replaying a corrupted audit chain.

    Malformed lines: logged at WARNING and skipped (permissive; see module docstring).
    Missing file: yields nothing.
    """
    if not journal_path.exists():
        return
    prev_seq: int | None = None
    try:
        with journal_path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = JournalEntry.model_validate_json(stripped)
                except (ValueError, TypeError) as e:
                    _logger.warning(
                        "malformed journal line at %s:%d: %s — skipping",
                        journal_path,
                        lineno,
                        e,
                    )
                    continue
                # Second-line-of-defence monotonicity check (writer is first).
                if prev_seq is not None and entry.monotonic_seq <= prev_seq:
                    raise JournalError(
                        f"journal seq regression at {journal_path}:{lineno}:"
                        f" {entry.monotonic_seq} <= {prev_seq}",
                        details={
                            "path": str(journal_path),
                            "step": "reader_invariant",
                            "prev_seq": prev_seq,
                            "next_seq": entry.monotonic_seq,
                            "lineno": lineno,
                        },
                    )
                prev_seq = entry.monotonic_seq
                yield entry
    except JournalError:
        raise
    except OSError as e:
        # Outer wrap also covers OSError from the with-block's __exit__ (close-on-GC,
        # NFS stale handle, etc.) so callers always see JournalError, not bare OSError.
        raise JournalError(
            f"journal read failed: {e}",
            details={"path": str(journal_path), "errno": e.errno, "step": "read_journal"},
        ) from e


def iter_after(journal_path: Path, threshold: int) -> Iterator[JournalEntry]:
    """Yield entries with monotonic_seq strictly greater than threshold.

    Useful for incremental projection (Story 1.12 will call this with the last-seen seq).
    Validates ``threshold`` is ``int`` so a string-coerced value can't trigger a
    mid-iteration ``TypeError`` (review patch Edge M5).
    """
    if not isinstance(threshold, int) or isinstance(threshold, bool):
        raise JournalError(
            f"iter_after: threshold must be int (got {type(threshold).__name__})",
            details={
                "path": str(journal_path),
                "step": "validate_threshold",
                "errno": None,
                "supplied_type": type(threshold).__name__,
            },
        )
    for entry in iter_entries(journal_path):
        if entry.monotonic_seq > threshold:
            yield entry

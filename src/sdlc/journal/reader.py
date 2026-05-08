"""POSIX-cross-platform journal reader: pure read, no flock required (Architecture §522, §1060).

Reads sort strictly by monotonic_seq; order in file IS the order returned (O_APPEND guarantees).

Trade-off: malformed lines are skipped with a stderr warning (permissive reader) to support
Story 1.20's sdlc rebuild-state recovery path. Mitigation: JournalError(step="reader_invariant")
fires if seqs go out-of-order — the dangerous corruption case is still caught loudly.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError


def iter_entries(journal_path: Path) -> Iterator[JournalEntry]:
    """Yield JournalEntry records in file order (= monotonic_seq order by O_APPEND invariant).

    File order IS monotonic_seq order because the writer's validate_seq enforces strictly
    increasing seqs under flock. A second-line-of-defence assertion raises JournalError if
    a seq regression is detected — protecting downstream projection (Story 1.12) from
    silently replaying a corrupted audit chain.

    Malformed lines: printed to stderr and skipped (permissive; see module docstring).
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
                    print(
                        f"warning: malformed journal line at {journal_path}:{lineno}: {e}"
                        " — skipping",
                        file=sys.stderr,
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
        raise JournalError(
            f"journal read failed: {e}",
            details={"path": str(journal_path), "errno": e.errno, "step": "read_journal"},
        ) from e


def iter_after(journal_path: Path, threshold: int) -> Iterator[JournalEntry]:
    """Yield entries with monotonic_seq strictly greater than threshold.

    Useful for incremental projection (Story 1.12 will call this with the last-seen seq).
    """
    for entry in iter_entries(journal_path):
        if entry.monotonic_seq > threshold:
            yield entry

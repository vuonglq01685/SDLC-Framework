from __future__ import annotations

import sys
from pathlib import Path

# writer.py is POSIX-only (fcntl + O_APPEND); reader.py is cross-platform (pure file read).
# On Windows the names exist at import time but append/append_sync raise JournalError,
# while iter_entries/iter_after remain functional (no flock needed for read-only access).
if sys.platform != "win32":
    from sdlc.journal.writer import append, append_sync
else:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.errors import JournalError

    _WIN_MSG = (
        "sdlc.journal.append is POSIX-only — see Architecture §573, §493."
        " Windows does not expose fcntl/O_APPEND atomicity."
    )

    async def append(entry: JournalEntry, journal_path: Path) -> None:
        raise JournalError(
            _WIN_MSG,
            details={
                "path": str(journal_path),
                "errno": None,
                "step": "windows_unsupported",
                "monotonic_seq": entry.monotonic_seq,
            },
        )

    def append_sync(entry: JournalEntry, journal_path: Path) -> None:
        raise JournalError(
            _WIN_MSG.replace("append", "append_sync"),
            details={
                "path": str(journal_path),
                "errno": None,
                "step": "windows_unsupported",
                "monotonic_seq": entry.monotonic_seq,
            },
        )


from sdlc.journal.reader import iter_after, iter_entries

# Semantic order: write (async) → write (sync) → read-all → read-after; do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "append",
    "append_sync",
    "iter_entries",
    "iter_after",
)

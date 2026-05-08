from __future__ import annotations

import sys

# writer.py is POSIX-only (fcntl + O_APPEND); reader.py is cross-platform (pure file read).
# On Windows the names exist at import time but append/append_sync raise NotImplementedError,
# while iter_entries/iter_after remain functional (no flock needed for read-only access).
if sys.platform != "win32":
    from sdlc.journal.writer import append, append_sync
else:

    async def append(*_: object, **__: object) -> None:
        raise NotImplementedError("sdlc.journal.append is POSIX-only — see Architecture §573, §493")

    def append_sync(*_: object, **__: object) -> None:
        raise NotImplementedError(
            "sdlc.journal.append_sync is POSIX-only — see Architecture §573, §493"
        )


from sdlc.journal.reader import iter_after, iter_entries

# Semantic order: write (async) → write (sync) → read-all → read-after; do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "append",
    "append_sync",
    "iter_entries",
    "iter_after",
)

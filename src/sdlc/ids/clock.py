"""RFC 3339 UTC clock helper (Story 2A.8 — hooks/ may not import cli/).

Shared across journal timestamps, hook bypass entries, and CLI writers so
wire-format timestamps stay byte-identical. Formerly ``cli/_time.py``; moved
to ``ids/`` because ``hooks/`` forbids ``cli/`` per Architecture §1109.
"""

from __future__ import annotations

import datetime


def now_rfc3339_utc_ms() -> str:
    """Return current UTC time as RFC 3339 with millisecond precision + ``Z`` suffix.

    Format: ``YYYY-MM-DDTHH:MM:SS.mmmZ`` — matches the ms-precision regex
    enforced by ``JournalEntry._RFC3339_UTC`` and ``_HookHashStore.trusted_at``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


__all__ = ["now_rfc3339_utc_ms"]

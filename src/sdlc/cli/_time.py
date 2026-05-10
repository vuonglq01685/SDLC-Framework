"""RFC 3339 UTC time helper shared across CLI write sites (P13).

Single source of truth so wire-format timestamps are byte-identical across all
producers (``scan``, ``trust-hooks``, ``init``, future commands). Previously
duplicated in three modules with subtly drifting implementations.
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

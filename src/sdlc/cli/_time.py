"""RFC 3339 UTC time helper — re-exports ``ids.clock`` for CLI call sites (P13)."""

from __future__ import annotations

from sdlc.ids.clock import now_rfc3339_utc_ms

__all__ = ["now_rfc3339_utc_ms"]

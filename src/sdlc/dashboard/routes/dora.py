"""``GET /api/dora`` — synthetic DORA envelope with 30 s in-memory cache (Story 5.1 AC3)."""

from __future__ import annotations

import json
import threading
import time
from typing import Final

from sdlc.dashboard.router import RequestContext, Response, Router

_CACHE_TTL_SECONDS: Final[float] = 30.0
_SYNTHETIC_BODY: Final[bytes] = json.dumps(
    {
        "schema_version": 1,
        "synthetic": True,
        "deployment_frequency": {"7d": 0, "30d": 0},
        "lead_time_hours": {"7d": 0.0, "30d": 0.0},
        "change_failure_rate": {"7d": 0.0, "30d": 0.0},
        "mean_time_to_recovery_hours": {"7d": 0.0, "30d": 0.0},
    },
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")


class _DoraCache:
    """Thread-safe 30 s TTL cache for the synthetic DORA payload.

    The dashboard runs under ``ThreadingHTTPServer`` (one thread per connection,
    sharing one cache), so the check-then-set in :meth:`get` is guarded by a lock
    (CR5.1 review R5 — the prior "single-threaded" comment was incorrect).
    """

    __slots__ = ("_body", "_expires_at", "_lock")

    def __init__(self) -> None:
        self._body: bytes | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> bytes:
        with self._lock:
            now = time.monotonic()
            if self._body is None or now >= self._expires_at:
                self._body = _SYNTHETIC_BODY
                self._expires_at = now + _CACHE_TTL_SECONDS
            return self._body


def register_dora_route(router: Router) -> _DoraCache:
    cache = _DoraCache()

    @router.get("/api/dora")
    def handle_dora(_ctx: RequestContext) -> Response:
        body = cache.get()
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )

    return cache

"""``GET /api/dora`` — real DORA compute wired behind a 30 s in-memory cache.

Story 5.1 froze the route + cache seam (30 s TTL, ``threading.Lock``,
``time.monotonic()``, per-project single cache — DD-05). Story 5.13 replaces
the synthetic body with the real compute call: ``telemetry.dora.compute_dora_window``
reads ``agent_runs.jsonl`` via its own reader seam (D2) and is fed pre-read
git commit tuples injected from the ``cli`` layer at server construction
(D1 — ``dashboard``/``telemetry`` may not invoke a subprocess or import
``cli``). See ``docs/api/dora-schema.json`` for the response envelope
(internal/documentary schema, DAG Decision D1(a) — freeze stays 7/7).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.telemetry.dora import GitCommitTuple, compute_dora_window

_CACHE_TTL_SECONDS: Final[float] = 30.0
_AGENT_RUNS_PATH_REL: Final[str] = "03-Implementation/agent_runs.jsonl"


def _default_git_log_provider() -> list[GitCommitTuple]:
    """No git-log provider injected → empty history → `insufficient_data` (graceful)."""
    return []


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class _DoraCache:
    """Thread-safe 30 s TTL cache holding the last-computed DORA body.

    The dashboard runs under ``ThreadingHTTPServer`` (one thread per
    connection, sharing one cache), so the check-then-set in :meth:`get` is
    guarded by a lock (CR5.1 review R5). ``get`` now takes the compute
    callback so the cached content can come from the real engine (5.13)
    instead of a fixed constant (5.1) while the TTL/lock contract is
    unchanged.
    """

    __slots__ = ("_body", "_expires_at", "_lock")

    def __init__(self) -> None:
        self._body: bytes | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get(self, compute: Callable[[], bytes]) -> bytes:
        with self._lock:
            now = time.monotonic()
            if self._body is None or now >= self._expires_at:
                self._body = compute()
                self._expires_at = now + _CACHE_TTL_SECONDS
            return self._body


def register_dora_route(
    router: Router,
    *,
    repo_root: Path,
    git_log_provider: Callable[[], Sequence[GitCommitTuple]] | None = None,
    clock: Callable[[], datetime] = _default_clock,
) -> _DoraCache:
    cache = _DoraCache()
    agent_runs_path = repo_root / _AGENT_RUNS_PATH_REL
    provider = git_log_provider if git_log_provider is not None else _default_git_log_provider

    def _compute_body() -> bytes:
        result = compute_dora_window(
            agent_runs_path=agent_runs_path,
            git_commits=provider(),
            now=clock(),
        )
        return json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @router.get("/api/dora")
    def handle_dora(_ctx: RequestContext) -> Response:
        body = cache.get(_compute_body)
        return Response(
            status=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )

    return cache

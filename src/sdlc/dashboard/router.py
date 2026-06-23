"""Decorator-style micro-router for the dashboard HTTP server (Decision E1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

_WRITE_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "DELETE", "PATCH"})


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Per-request context passed to route handlers."""

    method: str
    path: str
    headers: Mapping[str, str]
    repo_root: Path
    static_root: Path


@dataclass(frozen=True, slots=True)
class Response:
    """HTTP response returned by a route handler."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


RouteHandler = Callable[[RequestContext], Response]


class Router:
    """Minimal method+path router (~30 LOC core)."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], RouteHandler] = {}

    def route(self, method: str, path: str) -> Callable[[RouteHandler], RouteHandler]:
        key = (method.upper(), path)

        def decorator(handler: RouteHandler) -> RouteHandler:
            self._routes[key] = handler
            return handler

        return decorator

    def get(self, path: str) -> Callable[[RouteHandler], RouteHandler]:
        return self.route("GET", path)

    def dispatch(self, ctx: RequestContext) -> RouteHandler | None:
        return self._routes.get((ctx.method, ctx.path))

    def is_write_method(self, method: str) -> bool:
        return method.upper() in _WRITE_METHODS

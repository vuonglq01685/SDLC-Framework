"""Micro-router unit tests (novel substrate — test-along)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.dashboard.router import RequestContext, Response, Router

pytestmark = pytest.mark.unit


def _ctx(*, method: str = "GET", path: str = "/x") -> RequestContext:
    return RequestContext(
        method=method,
        path=path,
        headers={},
        repo_root=Path("/repo"),
        static_root=Path("/repo/static"),
    )


class TestRouter:
    def test_registers_and_dispatches_get(self) -> None:
        router = Router()
        seen: list[str] = []

        @router.get("/hello")
        def hello(_ctx: RequestContext) -> Response:
            seen.append("ok")
            return Response(status=200, body=b"hi")

        handler = router.dispatch(_ctx(path="/hello"))
        assert handler is not None
        response = handler(_ctx(path="/hello"))
        assert response.status == 200
        assert seen == ["ok"]

    def test_unknown_path_returns_none(self) -> None:
        router = Router()
        assert router.dispatch(_ctx(path="/missing")) is None

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
    def test_write_methods_flagged(self, method: str) -> None:
        router = Router()
        assert router.is_write_method(method) is True

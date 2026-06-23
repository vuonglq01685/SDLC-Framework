"""``GET /state.json`` — stream state file as-is with ETag/304 (Story 5.1 AC2)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from sdlc.dashboard.etag import compute_etag
from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.errors import SignoffError

_STATE_REL: Final[str] = ".claude/state/state.json"


def register_state_route(router: Router, *, repo_root: Path) -> None:
    state_path = repo_root / _STATE_REL

    @router.get("/state.json")
    def handle_state_json(ctx: RequestContext) -> Response:
        if not state_path.is_file():
            return Response(status=404, body=b"Not Found")

        try:
            etag = compute_etag(state_path, repo_root=repo_root)
        except SignoffError:
            return Response(status=404, body=b"Not Found")

        if not etag:
            return Response(status=404, body=b"Not Found")

        if_none_match = ctx.headers.get("If-None-Match", "")
        if if_none_match == etag:
            return Response(status=304, headers={"ETag": etag})

        body = state_path.read_bytes()
        return Response(
            status=200,
            headers={"ETag": etag, "Content-Type": "application/json; charset=utf-8"},
            body=body,
        )

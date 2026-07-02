"""``GET /api/backlog`` — real hierarchy read seam wire-up (Story 5.15 Task 1/2).

Covers the server-side wiring: the route is reachable, returns the exact
``{currentTaskId, epics:[...]}`` envelope the FROZEN 5.10 ``renderBacklogTree``
consumes, and is unaffected by an absent artifact tree (fresh project).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.cli._epic_story_models import _EpicEntry, serialize_entry
from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

from ._http import http_get

pytestmark = pytest.mark.unit

_DRAFTED_AT = "2026-07-01T00:00:00.000Z"


def _write_epic(root: Path, *, id_: str, label: str) -> None:
    entry = _EpicEntry(
        id=id_,
        label=label,
        priority="P1",
        ordering=0,
        acceptance_criteria=("Criterion 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="epic-generator",
    )
    path = root / "01-Requirement/04-Epics" / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _start_dashboard(repo_root: Path) -> tuple[str, int, object, object]:
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=repo_root, port=port)
    base_url = f"http://127.0.0.1:{port}"
    return base_url, port, server, thread


def _stop_dashboard(server: object, thread: object) -> None:
    server.shutdown()  # type: ignore[attr-defined]
    server.server_close()  # type: ignore[attr-defined]
    thread.join(timeout=5)  # type: ignore[attr-defined]


def test_route_is_reachable_and_returns_json(tmp_path: Path) -> None:
    base_url, port, server, thread = _start_dashboard(tmp_path)
    try:
        status, headers, body = http_get(base_url, "/api/backlog", port=port)
        assert status == 200
        assert "application/json" in headers["content-type"]
        payload = json.loads(body.decode("utf-8"))
        assert payload == {"currentTaskId": "", "epics": []}
    finally:
        _stop_dashboard(server, thread)


def test_route_reflects_real_epic_on_disk(tmp_path: Path) -> None:
    _write_epic(tmp_path, id_="EPIC-stripe-webhook", label="Stripe webhook pipeline")
    base_url, port, server, thread = _start_dashboard(tmp_path)
    try:
        _, _, body = http_get(base_url, "/api/backlog", port=port)
        payload = json.loads(body.decode("utf-8"))
        assert len(payload["epics"]) == 1
        assert payload["epics"][0]["id"] == "EPIC-stripe-webhook"
        assert payload["epics"][0]["name"] == "Stripe webhook pipeline"
        assert payload["epics"][0]["kind"] == "EPIC"
    finally:
        _stop_dashboard(server, thread)


def test_route_never_reads_state_json_for_the_hierarchy(tmp_path: Path) -> None:
    """D1: state.json's stories/tasks are always empty (projection gap) -- the
    route must not depend on them being populated."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        json.dumps({"schema_version": 1, "phase": 1, "epics": {}, "stories": {}, "tasks": {}}),
        encoding="utf-8",
    )
    _write_epic(tmp_path, id_="EPIC-x", label="X")
    base_url, port, server, thread = _start_dashboard(tmp_path)
    try:
        _, _, body = http_get(base_url, "/api/backlog", port=port)
        payload = json.loads(body.decode("utf-8"))
        assert len(payload["epics"]) == 1
    finally:
        _stop_dashboard(server, thread)

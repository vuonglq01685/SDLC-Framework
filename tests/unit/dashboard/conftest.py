"""Shared fixtures for dashboard HTTP tests."""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

from ._http import http_get, http_request

pytestmark = pytest.mark.unit

__all__ = ("dashboard_project", "http_get", "http_request", "running_dashboard")


@pytest.fixture()
def dashboard_project(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
    return tmp_path


@pytest.fixture()
def running_dashboard(
    dashboard_project: Path,
) -> Generator[tuple[str, int, object], None, None]:
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=dashboard_project, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            status, _, _ = http_get(base_url, "/state.json", port=port)
            if status in {200, 404}:
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    yield base_url, port, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)

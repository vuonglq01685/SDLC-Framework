"""Route behaviour tests for dashboard read endpoints (Story 5.1 AC2-AC3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ._http import http_get

pytestmark = pytest.mark.unit


class TestStateJsonRoute:
    def test_streams_state_file_as_is(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, headers, body = http_get(base_url, "/state.json", port=port)
        assert status == 200
        assert headers.get("content-type", "").startswith("application/json")
        assert body == b'{"phase":1}'
        assert headers.get("etag", "").startswith("sha256:")

    def test_returns_304_when_etag_matches(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        _, headers, _ = http_get(base_url, "/state.json", port=port)
        etag = headers["etag"]
        status, _, body = http_get(
            base_url, "/state.json", port=port, headers={"If-None-Match": etag}
        )
        assert status == 304
        assert body == b""

    def test_returns_new_etag_after_content_change(
        self, running_dashboard: tuple[str, int, object], dashboard_project
    ) -> None:
        base_url, port, _ = running_dashboard
        _, headers, _ = http_get(base_url, "/state.json", port=port)
        old_etag = headers["etag"]
        state_path = dashboard_project / ".claude" / "state" / "state.json"
        state_path.write_text('{"phase":2}', encoding="utf-8")
        status, headers, body = http_get(base_url, "/state.json", port=port)
        assert status == 200
        assert body == b'{"phase":2}'
        assert headers["etag"] != old_etag

    def test_missing_state_file_returns_404(
        self, dashboard_project: Path, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        state_path = dashboard_project / ".claude" / "state" / "state.json"
        state_path.unlink()
        status, _, _ = http_get(base_url, "/state.json", port=port)
        assert status == 404


class TestDoraRoute:
    def test_returns_synthetic_json(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, headers, body = http_get(base_url, "/api/dora", port=port)
        assert status == 200
        assert headers.get("content-type", "").startswith("application/json")
        payload = json.loads(body.decode("utf-8"))
        assert payload["synthetic"] is True
        assert payload["schema_version"] == 1

    def test_cache_serves_same_payload_on_rapid_requests(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status1, _, body1 = http_get(base_url, "/api/dora", port=port)
        status2, _, body2 = http_get(base_url, "/api/dora", port=port)
        assert status1 == status2 == 200
        assert body1 == body2
        assert json.loads(body1.decode("utf-8"))["synthetic"] is True

    def test_dora_cache_holds_within_ttl_and_refreshes_after_expiry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Inject a controllable clock so the refresh branch is observable — a constant
        # payload makes value-equality tautological (CR5.1 review R7); assert on the
        # TTL expiry boundary instead.
        from sdlc.dashboard.routes import dora as dora_mod

        clock = {"now": 1000.0}
        monkeypatch.setattr(dora_mod.time, "monotonic", lambda: clock["now"])
        monkeypatch.setattr(dora_mod, "_CACHE_TTL_SECONDS", 30.0)
        cache = dora_mod._DoraCache()

        cache.get()
        first_expiry = cache._expires_at
        assert first_expiry == 1030.0

        # within TTL → served from cache, expiry unchanged
        clock["now"] = 1020.0
        cache.get()
        assert cache._expires_at == first_expiry

        # past TTL → refreshed, expiry advances (would fail if the refresh branch broke)
        clock["now"] = 1031.0
        cache.get()
        assert cache._expires_at == 1061.0

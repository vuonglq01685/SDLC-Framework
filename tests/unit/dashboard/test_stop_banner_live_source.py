"""Static-analysis contract for STOP banner live poller (Story 5.19)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_LIVE_JS = _COMPONENTS / "stop-banner" / "stop-banner-live.js"
_FIXTURE = _COMPONENTS / "stop-banner" / "stop-banner-live.fixture.html"
_BANNER_JS = _COMPONENTS / "stop-banner" / "stop-banner.js"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code_only(js: str) -> str:
    return _BLOCK_COMMENT.sub("", js)


def test_live_module_exists() -> None:
    assert _LIVE_JS.is_file(), f"missing {_LIVE_JS.relative_to(_REPO_ROOT)}"


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_poll_cadence_is_3000ms() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert re.search(r"POLL_INTERVAL_MS\s*=\s*3_?000\b", js)
    assert "setInterval" in js


def test_reads_state_json_stop_slice() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    banner_js = _BANNER_JS.read_text(encoding="utf-8")
    assert "/state.json" in js
    assert "auto_loop_status" in banner_js
    assert "stop_reason" in banner_js


def test_never_replaces_alerts_host_wholesale() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert not re.search(r"\.innerHTML\s*=", js), "no innerHTML wholesale replacement"


def test_content_delta_signature_guarded() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    assert "lastSignature" in js or "signature" in js
    assert "triggersSignature" in js or "JSON.stringify" in js


def test_empty_state_when_zero_active_stops() -> None:
    js = _LIVE_JS.read_text(encoding="utf-8")
    banner_js = _BANNER_JS.read_text(encoding="utf-8")
    assert "renderStopBanners" in js
    assert "renderEmptyState" in banner_js or "empty-state" in banner_js


def test_poller_hardening_in_flight_abort_dispose() -> None:
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    assert re.search(r"if\s*\(\s*inFlight", js)
    assert "AbortController" in js
    assert re.search(r"\.abort\(\s*\)", js)
    assert "disposed" in js


def test_no_engine_import() -> None:
    js = _code_only(_LIVE_JS.read_text(encoding="utf-8"))
    assert "engine" not in js.lower()


def test_fixture_imports_poller() -> None:
    fixture = _FIXTURE.read_text(encoding="utf-8")
    assert "startStopBannerLivePoller" in fixture
    assert "stop-banner-live.js" in fixture


def test_banner_js_mapping_covers_all_seven_registry_triggers() -> None:
    js = _BANNER_JS.read_text(encoding="utf-8")
    for trigger_id in (
        "high_risk_path",
        "agent_failed",
        "open_clarification",
        "signoff_required",
        "replan_dirty",
        "bug_awaiting_decide",
        "pr_ready_story",
    ):
        assert trigger_id in js

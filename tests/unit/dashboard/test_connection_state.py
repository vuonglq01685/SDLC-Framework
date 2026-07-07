"""Static-analysis contract for the connection-state broker (Story 5.20).

Mirrors ``test_phase_tracker_live_source.py`` (PAT-3): measures the broker's
JS source-of-truth rather than executing it (Playwright covers behavioral
witness in ``tests/integration/test_dashboard_connection_state.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_BROKER_JS = _COMPONENTS / "connection-state" / "connection-state.js"
_FIXTURE = _COMPONENTS / "connection-state" / "connection-state.fixture.html"
_MASTHEAD_JS = _COMPONENTS / "masthead" / "masthead.js"
_RESUME_LIVE_JS = _COMPONENTS / "resume-card" / "resume-card-live.js"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code_only(js: str) -> str:
    return _BLOCK_COMMENT.sub("", js)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_broker_module_exists() -> None:
    assert _BROKER_JS.is_file()


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_disconnect_threshold_is_three() -> None:
    js = _read(_BROKER_JS)
    assert re.search(r"DISCONNECT_THRESHOLD\s*=\s*3\b", js), (
        "broker must document N=3 consecutive failures (§7.11, D3)"
    )


def test_broker_exports_report_subscribe_get_state() -> None:
    js = _read(_BROKER_JS)
    export_block = _export_block(js)
    assert export_block, "broker must have an `export { ... }` block"
    for name in ("reportPollResult", "subscribe", "getState"):
        assert name in export_block, f"broker must export {name}"
    assert '"disconnected"' in js
    assert '"default"' in js


def test_broker_is_frontend_only_no_server_route() -> None:
    js = _code_only(_read(_BROKER_JS))
    assert "/api/" not in js
    assert "engine" not in js.lower()


def test_masthead_reports_poll_results_to_broker() -> None:
    js = _read(_MASTHEAD_JS)
    assert "connection-state" in js
    assert "reportPollResult" in js


def test_masthead_reports_ok_on_304_path() -> None:
    """D3: a 304 is success — broker must see ok:true before the early return.

    Witnesses ORDERING inside the real tick body: a naive ``js.find`` matches the
    top-of-file ``import { ... reportPollResult ... }`` and is vacuously true, so
    a regression that returns on 304 before reporting would slip through.
    """
    js = _read(_MASTHEAD_JS)
    tick_body = _tick_body(js)
    assert tick_body, "could not locate the masthead tick body"
    ok_match = re.search(r"reportPollResult\(\s*\{\s*ok:\s*true", tick_body)
    null_match = re.search(r"json\s*==\s*null", tick_body)
    assert ok_match, "tick must report ok:true on a resolved poll"
    assert null_match, "tick must early-return on a 304 (json == null)"
    assert ok_match.start() < null_match.start(), (
        "304 is success (D3): reportPollResult({ok:true}) must run BEFORE the "
        "`json == null` early return, else a 304 is dropped as neither success "
        "nor failure and the recover-in-one-poll contract (AC2) breaks"
    )


def test_resume_card_live_subscribes_to_broker() -> None:
    js = _read(_RESUME_LIVE_JS)
    assert "connection-state" in js
    assert "subscribe" in js


def test_honest_disconnection_banner_reuses_alert_treatment() -> None:
    js = _read(_BROKER_JS)
    assert "renderHonestDisconnectionBanner" in js
    assert "alert" in js
    assert "Dashboard cannot reach state" in js


def test_fixture_imports_broker_and_wires_simulation_api() -> None:
    html = _read(_FIXTURE)
    assert "connection-state.js" in html
    assert "__connectionFixture" in html
    assert "simulateFailure" in html


def _tick_body(js: str) -> str:
    """The masthead poll ``tick`` arrow-function body (up to its ``tick()`` call)."""
    start = js.find("const tick = async")
    if start == -1:
        return ""
    end = js.find("\n  tick();", start)
    return js[start:end] if end != -1 else js[start:]


def _export_block(js: str) -> str:
    """Contents of the module's ``export { ... }`` block (empty if none)."""
    match = re.search(r"export\s*\{([^}]*)\}", js)
    return match.group(1) if match else ""

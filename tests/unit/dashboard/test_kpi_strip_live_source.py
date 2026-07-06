"""Static-analysis contract for the KPI Strip real-data poller (Story 5.17).

Mirrors ``test_resume_card_live_source.py`` (PAT-3): measures the poller's
JS source-of-truth rather than executing it (Playwright covers rendered DOM
behavior in ``tests/integration/test_dashboard_kpi_strip_live.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_LIVE_JS = _COMPONENTS / "kpi-strip" / "kpi-strip-live.js"
_FIXTURE = _COMPONENTS / "kpi-strip" / "kpi-strip-live.fixture.html"
_KPI_JS = _COMPONENTS / "kpi-strip" / "kpi-strip.js"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code_only(js: str) -> str:
    return _BLOCK_COMMENT.sub("", js)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_live_module_exists() -> None:
    assert _LIVE_JS.is_file()


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_poll_cadence_is_3000ms() -> None:
    js = _read(_LIVE_JS)
    assert re.search(r"POLL_INTERVAL_MS\s*=\s*3_?000\b", js)
    assert "setInterval" in js


def test_reads_the_api_dora_seam_not_state_json() -> None:
    js = _read(_LIVE_JS)
    assert "/api/dora" in js
    assert "/state.json" not in _code_only(js)


def test_reuses_render_kpi_strip_seam_untouched() -> None:
    js = _read(_LIVE_JS)
    assert 'import { renderKpiStrip } from "./kpi-strip.js"' in js


def test_has_in_flight_guard_and_abort_controller() -> None:
    js = _read(_LIVE_JS)
    assert "inFlight" in js
    assert "AbortController" in js
    assert ".abort()" in js


def test_has_loading_state_rendered_before_first_poll_resolves() -> None:
    js = _read(_LIVE_JS)
    assert "LOADING_CELLS" in js


def test_dispose_stops_interval_and_aborts_and_sets_stop_poller_hook() -> None:
    js = _read(_LIVE_JS)
    assert "clearInterval" in js
    assert "host._stopPoller = dispose" in js


def test_does_not_import_kpi_strip_live_from_kpi_strip_js() -> None:
    """Avoid a circular ES-module dependency: kpi-strip.js stays one-directional."""
    js = _read(_KPI_JS)
    assert not re.search(r"""(?:import|from)\s*['"].*kpi-strip-live""", js)


def test_fixture_mounts_kpi_strip_with_live_source_and_imports_poller() -> None:
    html = _read(_FIXTURE)
    assert 'id="kpi-strip-live-target"' in html
    assert 'data-source="live"' in html
    assert "kpi-strip-live.js" in html
    assert "startKpiStripLivePoller" in html

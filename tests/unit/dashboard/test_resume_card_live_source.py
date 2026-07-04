"""Static-analysis contract for the Resume Card real-data poller (Story 5.18).

Mirrors ``test_backlog_tree_live_source.py`` (PAT-3): measures the poller's
JS/HTML source-of-truth rather than executing it (Playwright covers rendered
DOM behavior in ``tests/integration/test_dashboard_resume_card_live.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPONENTS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "components"
_LIVE_JS = _COMPONENTS / "resume-card" / "resume-card-live.js"
_FIXTURE = _COMPONENTS / "resume-card" / "resume-card-live.fixture.html"
_RESUME_JS = _COMPONENTS / "resume-card" / "resume-card.js"

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


def test_reads_the_api_resume_seam_not_state_json() -> None:
    """D1(b): the real cursor/breadcrumb comes from the dedicated route."""
    js = _read(_LIVE_JS)
    assert "/api/resume" in js
    assert "/state.json" not in _code_only(js), (
        "must NOT fold the resume token into /state.json (D1)"
    )


def test_reuses_render_resume_card_seam_untouched() -> None:
    js = _read(_LIVE_JS)
    assert 'import { renderResumeCard } from "./resume-card.js"' in js


def test_has_in_flight_guard_and_abort_controller() -> None:
    """Masthead DEF-1 fold: skip overlapping ticks AND abort on disconnect."""
    js = _read(_LIVE_JS)
    assert "inFlight" in js
    assert "AbortController" in js
    assert ".abort()" in js


def test_has_loading_fixture_rendered_before_first_poll_resolves() -> None:
    """Masthead DEF-3 fold: a neutral loading state, never a blank card."""
    js = _read(_LIVE_JS)
    assert "LOADING_FIXTURE" in js
    assert 'variant: "loading"' in js


def test_dispose_stops_interval_and_aborts_and_sets_stop_poller_hook() -> None:
    js = _read(_LIVE_JS)
    assert "clearInterval" in js
    assert "host._stopPoller = dispose" in js


def test_does_not_import_resume_card_live_from_resume_card_js() -> None:
    """Avoid a circular ES-module dependency: resume-card.js must stay a
    one-directional base module (mirrors backlog-tree.js / backlog-tree-live.js)."""
    js = _read(_RESUME_JS)
    assert not re.search(r"""(?:import|from)\s*['"].*resume-card-live""", js)


def test_fixture_mounts_resume_card_with_live_source_and_imports_poller() -> None:
    html = _read(_FIXTURE)
    assert 'id="resume-card-live-target"' in html
    assert 'data-source="live"' in html
    assert "resume-card-live.js" in html
    assert "startResumeCardLivePoller" in html

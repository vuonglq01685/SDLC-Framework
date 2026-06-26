"""Static-analysis contract for masthead component (Story 5.6)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_MASTHEAD_JS = _STATIC / "components" / "masthead" / "masthead.js"
_MASTHEAD_CSS = _STATIC / "components" / "masthead" / "masthead.css"
_FIXTURE = _STATIC / "components" / "masthead" / "masthead.fixture.html"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _exported_names(js: str) -> set[str]:
    """Names actually listed in `export { ... }` blocks (not merely defined)."""
    names: set[str] = set()
    for block in re.findall(r"export\s*\{([^}]*)\}", js):
        for raw in block.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    return names


def test_masthead_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_masthead_js_exports_tab_title_formatter_and_rate_limiter() -> None:
    js = _read(_MASTHEAD_JS)
    assert "function formatTabTitle" in js
    assert "function createAriaLiveRateLimiter" in js
    exported = _exported_names(js)
    assert "formatTabTitle" in exported
    assert "createAriaLiveRateLimiter" in exported
    assert "POLL_INTERVAL_MS" in exported
    assert "3000" in js or "3_000" in js


def test_masthead_js_reuses_freshness_footer_format_local_time() -> None:
    js = _read(_MASTHEAD_JS)
    assert "formatLocalTime" in js
    assert "freshness-footer" in js


def test_masthead_js_maps_frozen_live_dot_variants() -> None:
    js = _read(_MASTHEAD_JS)
    for variant in ("default", "warn", "disconnected"):
        assert variant in js


def test_masthead_css_composes_display_and_label_mono_tokens() -> None:
    css = _read(_MASTHEAD_CSS)
    assert "--type-display-1-size" in css
    assert "--type-label-mono-size" in css
    assert "border-bottom" in css
    assert "var(--border-strong)" in css


def test_masthead_fixture_mounts_banner_and_poll_target() -> None:
    html = _read(_FIXTURE)
    assert "<sdlc-masthead" in html
    assert "masthead.js" in html
    assert "masthead.css" in html
    assert "live-dot" in html
    assert 'id="masthead-tab-title-target"' in html


def test_format_tab_title_uses_middle_dot_separator() -> None:
    js = _read(_MASTHEAD_JS)
    assert "\u00b7" in js or "\\u00b7" in js


def test_disconnected_sub_line_contract_in_js() -> None:
    js = _read(_MASTHEAD_JS)
    assert "DISCONNECTED" in js
    assert "LAST POLL" in js
    assert "UPDATED" in js

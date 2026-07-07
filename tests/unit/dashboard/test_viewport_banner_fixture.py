"""Static-analysis contract for the viewport degradation banner (Story 5.21).

Frontend-only component (matchMedia detection + sessionStorage dismiss). These
tests read the committed JS/CSS/fixture assets and assert the load-bearing
contract clauses of AC1-AC3 without a browser. Behavioral witnesses live in
``tests/dashboard/test_viewport_banner_a11y.py`` (Playwright).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_DIR = _STATIC / "components" / "viewport-banner"
_JS = _DIR / "viewport-banner.js"
_CSS = _DIR / "viewport-banner.css"
_FIXTURE = _DIR / "viewport-banner.fixture.html"
_INDEX = _STATIC / "index.html"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Exact copy, verbatim from AC1/AC2 + UX §8.2 (do NOT paraphrase).
_COPY_BELOW_1280 = (
    "Dashboard is optimized for screens \u2265 1280 px. "
    "Some elements may overflow below this width."
)
_COPY_BELOW_768 = (
    "This dashboard is desktop-only. Mobile / tablet are unsupported. "
    "Open on a screen \u2265 1280 px."
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """Blank ``/* */`` and ``//`` comments so negative assertions test CODE, not prose.

    The component intentionally *names* forbidden patterns in its doc comments
    (``hamburger``, ``createStopBannerElement``, ``transition:``) to explain what it
    does NOT do — those mentions must not false-trip the anti-pattern contracts.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def test_component_assets_exist() -> None:
    assert _JS.is_file()
    assert _CSS.is_file()
    assert _FIXTURE.is_file()


def test_js_exports_start_seam_and_copy_constants() -> None:
    js = _read(_JS)
    assert "export function startViewportBanner" in js or "startViewportBanner," in js
    assert _COPY_BELOW_1280 in js, "verbatim <1280 copy missing"
    assert _COPY_BELOW_768 in js, "verbatim <768 upgraded copy missing"


def test_matchmedia_boundaries_exact_and_injectable() -> None:
    """D2: two matchMedia queries with .98px exact boundaries, injectable factory."""
    js = _read(_JS)
    assert "(max-width: 1279.98px)" in js
    assert "(max-width: 767.98px)" in js
    assert "matchMedia" in js
    # Injected factory so tests drive boundaries deterministically.
    assert "mediaQueryFn" in js


def test_uses_change_listener_not_resize_churn() -> None:
    """D2: subscribe via matchMedia change events, never a resize handler."""
    js = _read(_JS)
    assert 'addEventListener("change"' in js
    assert '"resize"' not in js
    assert "'resize'" not in js
    assert "onresize" not in js


def test_dismiss_uses_session_storage_not_local() -> None:
    """D3/AC1: dismiss is session-scoped (reappears next load), guarded access."""
    js = _read(_JS)
    assert "sessionStorage" in js
    assert "localStorage" not in js
    assert "try" in js and "catch" in js


def test_dismiss_button_is_labelled_and_keyboard_reachable() -> None:
    """D3: a single dismiss <button> with aria-label='Dismiss' (native = focusable)."""
    js = _read(_JS)
    assert "aria-label" in js
    assert "Dismiss" in js
    assert '"button"' in js  # createElement("button") / type="button"
    assert "\u00d7" in js  # the multiplication-sign glyph used for the close control


def test_banner_is_role_status_not_aria_live_spam() -> None:
    """D3: informational banner is role=status; NOT re-announced on every resize."""
    js = _read(_JS)
    assert 'role", "status"' in js or 'role","status"' in js or '"status"' in js
    assert "aria-live" not in js


def test_render_sink_is_textcontent_never_innerhtml() -> None:
    js = _read(_JS)
    assert "textContent" in js
    assert "innerHTML" not in js


def test_no_layout_collapse_logic() -> None:
    """AC2: no hamburger / card-stacking / display:none collapse anywhere."""
    js = _strip_comments(_read(_JS))
    css = _strip_comments(_read(_CSS))
    for forbidden in ("hamburger", "display: none", "display:none"):
        assert forbidden not in js, f"layout-collapse hint {forbidden!r} in JS"
        assert forbidden not in css, f"layout-collapse hint {forbidden!r} in CSS"


def test_css_reuses_alert_info_blue_treatment_tokens_only() -> None:
    css = _read(_CSS)
    assert ".alert" in css
    assert ".info" in css or "info" in css
    assert "var(--blue)" in css
    assert "var(--paper)" in css
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert hex_colors == [], f"raw hex colours forbidden (tokens only): {hex_colors}"


def test_css_has_no_transition_dd14() -> None:
    css = _strip_comments(_read(_CSS))
    assert re.search(r"\btransition\s*:", css) is None
    assert re.search(r"@keyframes", css) is None


def test_not_built_from_stop_banner_element_d1() -> None:
    """D1: reuse the .alert CSS treatment, NOT createStopBannerElement."""
    js = _strip_comments(_read(_JS))
    assert "createStopBannerElement" not in js
    assert "TRIGGER_META" not in js


def test_fixture_drives_both_copies_via_injected_driver() -> None:
    fixture = _read(_FIXTURE)
    assert "startViewportBanner" in fixture
    # Deterministic: a fake matchMedia / MediaQueryList, never a real resize.
    assert "matchMedia" in fixture or "mediaQueryFn" in fixture


def test_index_html_links_stylesheet_when_banner_mounted() -> None:
    """P1 (review 2026-07-07): if index.html mounts the banner JS, it MUST also
    link viewport-banner.css — otherwise the banner renders unstyled on the real
    page (no --blue .alert.info treatment), a gap every fixture-based test misses.
    """
    html = _read(_INDEX)
    if "startViewportBanner" in html:
        assert "components/viewport-banner/viewport-banner.css" in html, (
            "index.html mounts the viewport banner but does not link its stylesheet"
        )


def test_packaging_force_include_present() -> None:
    """Task 4: the three new static assets ship via force-include (ADR-005)."""
    toml = _read(_PYPROJECT)
    for asset in ("viewport-banner.js", "viewport-banner.css", "viewport-banner.fixture.html"):
        needle = f"components/viewport-banner/{asset}"
        assert needle in toml, f"force-include missing {needle}"

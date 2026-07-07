"""Static-analysis contract for resume card + inverted command (Story 5.8)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"
_RESUME_JS = _STATIC / "components" / "resume-card" / "resume-card.js"
_RESUME_CSS = _STATIC / "components" / "resume-card" / "resume-card.css"
_INVERTED_CSS = _STATIC / "components" / "inverted-command" / "inverted-command.css"
_FIXTURE = _STATIC / "components" / "resume-card" / "resume-card.fixture.html"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing committed asset: {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _exported_names(js: str) -> set[str]:
    names: set[str] = set()
    for block in re.findall(r"export\s*\{([^}]*)\}", js):
        for raw in block.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    return names


def test_resume_card_fixture_exists() -> None:
    assert _FIXTURE.is_file()


def test_resume_card_js_exports_normalize_command_and_greeting_helpers() -> None:
    js = _read(_RESUME_JS)
    assert "function normalizeCommand" in js
    exported = _exported_names(js)
    assert "normalizeCommand" in exported
    assert "shouldShowGreeting" in exported
    assert "markGreetingShown" in exported
    assert "renderResumeCard" in exported


def test_resume_card_js_exports_synthetic_fixture() -> None:
    js = _read(_RESUME_JS)
    assert "export const SYNTHETIC_RESUME_FIXTURE" in js


def test_resume_card_js_reuses_create_glyph_from_signoff_cell() -> None:
    js = _read(_RESUME_JS)
    assert "createGlyph" in js
    assert "signoff-cell" in js


def test_resume_card_js_reuses_freshness_footer() -> None:
    js = _read(_RESUME_JS)
    assert "freshness-footer" in js


def test_normalize_command_strips_whitespace_and_prefix_markers_in_js() -> None:
    js = _read(_RESUME_JS)
    assert "SHELL_PREFIX_RE" in js
    body = _fn_body(js, "normalizeCommand")
    assert ".trim()" in body
    assert "SHELL_PREFIX_RE" in body


def test_greeting_session_storage_contract_in_js() -> None:
    js = _read(_RESUME_JS)
    assert "sessionStorage" in js or "storage" in js
    assert "Welcome," in js


def test_resume_card_region_landmark_in_js() -> None:
    js = _read(_RESUME_JS)
    assert 'setAttribute("role", "region")' in js
    assert "Resume position and suggested command" in js


def test_copy_button_aria_label_and_clipboard_in_js() -> None:
    js = _read(_RESUME_JS)
    assert "Copy suggested command" in js
    assert "clipboard" in js
    assert "copy" in js
    assert "check" in js
    assert "copied to clipboard" in js


def test_resume_card_css_uses_paper_container_tokens() -> None:
    css = _read(_RESUME_CSS)
    assert "var(--paper)" in css
    assert "var(--border-hairline)" in css
    assert "var(--radius-xl)" in css
    assert "var(--space-12)" in css
    assert "var(--space-14)" in css
    assert "box-shadow: none" in css or "box-shadow:none" in css.replace(" ", "")


def test_inverted_command_surface_uses_ink_bg_and_bg_text() -> None:
    css = _read(_INVERTED_CSS)
    assert "var(--ink)" in css
    assert "var(--bg)" in css
    assert "var(--font-mono)" in css
    assert "var(--type-mono-md-size)" in css
    assert "var(--radius-md)" in css
    assert "var(--space-5)" in css
    assert "var(--space-6)" in css


def test_resume_card_eyebrow_tokens_in_css() -> None:
    css = _read(_RESUME_CSS)
    assert "--type-label-mono-sm-size" in css
    assert "var(--accent)" in css
    assert "var(--ink-mute)" in css
    assert "uppercase" in css


def test_copy_btn_minimum_target_size_in_css() -> None:
    css = _read(_INVERTED_CSS)
    assert "36px" in css
    assert ".copy-btn" in css


def test_fixture_mounts_resume_card_and_assets() -> None:
    html = _read(_FIXTURE)
    assert "<resume-card" in html
    assert "resume-card.js" in html
    assert "resume-card.css" in html
    assert "inverted-command.css" in html
    assert "freshness-footer" in html
    assert "tokens.css" in html
    assert "focus-motion.css" in html


def test_resume_card_css_values_are_token_var_only() -> None:
    """Stylelint contract: component CSS uses var(--*) except allowed literals."""
    css = _read(_RESUME_CSS) + _read(_INVERTED_CSS)
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert hex_colors == []
    # min 36px touch target on .copy-btn is an explicit a11y floor (Story 5.8 AC3).
    css_without_literals = re.sub(
        r"\.copy-btn\s*\{[^}]*\}",
        "",
        css,
        flags=re.DOTALL,
    )
    css_without_literals = re.sub(
        r"\.resume-card__sr-only\s*\{[^}]*\}",
        "",
        css_without_literals,
        flags=re.DOTALL,
    )
    raw_px = re.findall(r":\s*\d+px", css_without_literals)
    assert raw_px == []


def _fn_body(js: str, name: str) -> str:
    match = re.search(rf"function {name}\(.*?\)\s*\{{(.*?)\n\}}", js, re.DOTALL)
    assert match, f"{name} not found"
    return match.group(1)


def test_normalize_command_collapses_interior_newlines_in_js() -> None:
    """D5 (Story 5.18, folds 5.8 DEF-1): untrusted multi-line commands must
    collapse to a single space-joined line before they are ever copyable."""
    js = _read(_RESUME_JS)
    assert "INTERIOR_NEWLINE_RE" in js
    body = _fn_body(js, "normalizeCommand")
    assert "INTERIOR_NEWLINE_RE" in body


def test_bind_copy_button_stashes_reset_handle_on_timer_host() -> None:
    """DEF-8 timer lift: the copy-feedback reset timer lives on a caller-
    supplied persistent host, not a plain closure variable."""
    js = _read(_RESUME_JS)
    assert "timerHost" in js
    assert "_copyResetHandle" in js


def test_render_resume_card_announces_only_on_change() -> None:
    """DEF-5: poll-driven re-renders announce via the persistent live region
    only when the breadcrumb/command actually changed, never on first mount."""
    js = _read(_RESUME_JS)
    assert "_resumeCardAnnounced" in js
    assert "Updated —" in js


def test_resume_card_element_has_disconnected_callback_and_stop_poller_hook() -> None:
    js = _read(_RESUME_JS)
    assert "disconnectedCallback()" in js
    assert "_stopPoller" in js


def test_resume_card_element_coalesces_render_via_microtask() -> None:
    """DEF-8: attributeChangedCallback fires once per observed attribute (all
    before connectedCallback) -- must coalesce to a single _render() call."""
    js = _read(_RESUME_JS)
    assert "_scheduleRender()" in js
    assert "queueMicrotask" in js
    assert "_renderPending" in js


def test_resume_card_element_skips_auto_render_for_live_source() -> None:
    js = _read(_RESUME_JS)
    assert 'this.dataset.source === "live"' in js


def test_inverted_command_text_has_overflow_policy_in_css() -> None:
    """DEF-4 (Story 5.8, folded by 5.18): a long/real command must not
    overflow or awkwardly wrap inside the dark pill -- single-line, scrollable."""
    css = _read(_INVERTED_CSS)
    assert "overflow-x: auto" in css
    assert "white-space: pre" in css

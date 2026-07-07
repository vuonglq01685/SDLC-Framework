"""Static-analysis contract for resume card disconnected treatment (Story 5.20)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESUME_JS = (
    _REPO_ROOT
    / "src"
    / "sdlc"
    / "dashboard"
    / "static"
    / "components"
    / "resume-card"
    / "resume-card.js"
)
_RESUME_CSS = (
    _REPO_ROOT
    / "src"
    / "sdlc"
    / "dashboard"
    / "static"
    / "components"
    / "resume-card"
    / "resume-card.css"
)
_FIXTURE = (
    _REPO_ROOT
    / "src"
    / "sdlc"
    / "dashboard"
    / "static"
    / "components"
    / "resume-card"
    / "resume-card.fixture.html"
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_resume_card_js_handles_disconnected_variant() -> None:
    js = _read(_RESUME_JS)
    assert '"disconnected"' in js or "'disconnected'" in js
    assert "may be stale" in js.lower()


def test_resume_card_disconnected_disables_copy_button() -> None:
    js = _read(_RESUME_JS)
    assert "aria-disabled" in js
    assert "resume-card--disconnected" in js


def test_resume_card_css_has_amber_outline_for_disconnected() -> None:
    css = _read(_RESUME_CSS)
    assert "resume-card--disconnected" in css
    assert "var(--amber" in css


def test_resume_card_css_has_disabled_copy_visual() -> None:
    css = _read(_RESUME_CSS)
    assert "var(--ink-dim)" in css
    assert "resume-card__copy--disabled" in css


def test_fixture_has_disconnected_state_section() -> None:
    html = _read(_FIXTURE)
    assert 'variant="disconnected"' in html or "disconnected" in html.lower()


def test_resume_card_footer_uses_disconnected_variant() -> None:
    js = _read(_RESUME_JS)
    assert '"disconnected"' in js
    assert re.search(r"""setAttribute\(\s*["']variant["']""", js)

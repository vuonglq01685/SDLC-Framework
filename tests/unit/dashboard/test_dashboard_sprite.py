"""Contract tests for the 12-icon SVG sprite (Story 5.3 AC2 / DD-03)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SPRITE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "sdlc"
    / "dashboard"
    / "static"
    / "icons"
    / "sprite.svg"
)

_CANONICAL_IDS = frozenset(
    {
        "circle",
        "circle-filled",
        "check",
        "slash-circle",
        "arrow-right",
        "chevron-right",
        "chevron-down",
        "copy",
        "external-link",
        "info",
        "warning",
        "error",
    }
)


def test_sprite_contains_exactly_twelve_symbols() -> None:
    assert _SPRITE.is_file(), "sprite.svg must ship in the dashboard static tree"
    text = _SPRITE.read_text(encoding="utf-8")
    ids = set(re.findall(r'<symbol\s+id="([^"]+)"', text))
    assert ids == _CANONICAL_IDS
    assert len(ids) == 12


def test_sprite_header_documents_adr_trigger() -> None:
    text = _SPRITE.read_text(encoding="utf-8")
    header = re.search(r"<!--(.*?)-->", text, re.DOTALL)
    assert header is not None, "sprite.svg must carry a leading header comment"
    comment = header.group(1)
    # Scope to the comment block so the guard actually fails if the note is
    # removed (a bare ``"13" in text`` would match path coords like ``M13 6``).
    assert "13th" in comment.lower(), "header must document the 13th-icon ADR trigger"
    assert "ADR" in comment, "header must reference the ADR requirement"

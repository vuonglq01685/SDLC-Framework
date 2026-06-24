"""Font directory contract tests (Story 5.3 AC1 / DD-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_FONTS_DIR = Path(__file__).resolve().parents[3] / "src" / "sdlc" / "dashboard" / "static" / "fonts"

_EXPECTED_WOFF2 = frozenset(
    {
        "fraunces-400.woff2",
        "fraunces-500.woff2",
        "fraunces-600.woff2",
        "inter-300.woff2",
        "inter-400.woff2",
        "inter-500.woff2",
        "inter-600.woff2",
        "inter-700.woff2",
        "jetbrains-mono-400.woff2",
        "jetbrains-mono-500.woff2",
        "jetbrains-mono-600.woff2",
    }
)


def test_fonts_directory_contains_only_referenced_weights() -> None:
    assert _FONTS_DIR.is_dir(), "fonts/ must exist under dashboard static"
    woff2 = {p.name for p in _FONTS_DIR.glob("*.woff2")}
    assert woff2 == _EXPECTED_WOFF2
    assert len(woff2) == 11
    other_font_ext = [
        p.name
        for p in _FONTS_DIR.iterdir()
        if p.suffix.lower() in {".ttf", ".otf", ".woff"} and p.is_file()
    ]
    assert other_font_ext == []

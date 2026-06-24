"""Static asset serving tests for Story 5.3 (fonts MIME, /static/ prefix, cache)."""

from __future__ import annotations

import pytest

from sdlc.dashboard.server import resolve_static_file, static_root

from ._http import http_get

pytestmark = pytest.mark.unit

_STATIC = static_root()
_FONTS_DIR = _STATIC / "fonts"
_SPRITE = _STATIC / "icons" / "sprite.svg"


class TestStaticUrlConvention:
    """Decision D1 (option a): ``/static/`` prefix maps to package static root."""

    def test_static_prefix_resolves_sprite(self) -> None:
        if not _SPRITE.is_file():
            pytest.skip("sprite.svg not yet shipped")
        resolved = resolve_static_file("/static/icons/sprite.svg", static_dir=_STATIC)
        assert resolved == _SPRITE

    def test_static_prefix_resolves_signoff_fixture(self) -> None:
        fixture = _STATIC / "test-fixtures" / "signoff-states.html"
        if not fixture.is_file():
            pytest.skip("signoff-states.html not yet shipped")
        resolved = resolve_static_file(
            "/static/test-fixtures/signoff-states.html", static_dir=_STATIC
        )
        assert resolved == fixture

    def test_root_relative_sprite_still_resolves(self) -> None:
        if not _SPRITE.is_file():
            pytest.skip("sprite.svg not yet shipped")
        resolved = resolve_static_file("/icons/sprite.svg", static_dir=_STATIC)
        assert resolved == _SPRITE


class TestFontMimeTypes:
    def test_served_woff2_has_font_content_type(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        fonts = sorted(_FONTS_DIR.glob("*.woff2")) if _FONTS_DIR.is_dir() else []
        if not fonts:
            pytest.skip("no self-hosted fonts yet")
        sample = fonts[0].name
        base_url, port, _ = running_dashboard
        status, headers, _ = http_get(base_url, f"/static/fonts/{sample}", port=port)
        assert status == 200
        assert headers.get("content-type", "").startswith("font/woff2")


class TestImmutableCache:
    def test_sprite_served_with_immutable_cache(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        if not _SPRITE.is_file():
            pytest.skip("sprite.svg not yet shipped")
        base_url, port, _ = running_dashboard
        status, headers, _ = http_get(base_url, "/static/icons/sprite.svg", port=port)
        assert status == 200
        cache = headers.get("cache-control", "")
        assert "immutable" in cache
        assert "max-age=31536000" in cache

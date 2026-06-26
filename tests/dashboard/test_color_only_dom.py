"""Rendered-DOM color-only enforcement (Story 5.12 AC4 / closes 5.5 DEF-1)."""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import assert_live_dots_have_text_labels, with_playwright_page

pytestmark = [pytest.mark.integration]


def test_rendered_live_dots_pass_on_composite_fixture(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector("live-dot .live-dot__label")
        assert_live_dots_have_text_labels(page)


def test_color_only_dom_fails_without_label(dashboard_composite_url: str) -> None:
    # RED witness: live-dot.js self-renders a .live-dot__label on connect, so create
    # one on the (already live-dot-defining) composite page and strip the label to
    # simulate the DEF-1 failure mode — a color signal with no adjacent text.
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector("live-dot")
        page.evaluate(
            """() => {
              const dot = document.createElement('live-dot');
              dot.id = 'color-only-red-witness';
              document.body.appendChild(dot);
              const label = dot.querySelector('.live-dot__label');
              if (label) label.remove();
            }""",
        )
        with pytest.raises(AssertionError, match="live-dot without adjacent text label"):
            assert_live_dots_have_text_labels(page)

"""axe-core a11y harness for the dashboard composite fixture (Story 5.12 AC2)."""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import (
    assert_live_dots_have_text_labels,
    format_axe_violation,
    run_axe_scan,
    with_playwright_page,
)

pytestmark = [pytest.mark.integration]


def test_axe_scan_zero_level_a_violations_on_composite_fixture(
    dashboard_composite_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector("dashboard-tabs [role='tab']")
        page.wait_for_selector("backlog-tree .tree-expander")
        page.wait_for_selector("resume-card .copy-btn")
        blocking, reported = run_axe_scan(page)
        for violation in reported:
            print(f"AA-reported: {format_axe_violation(violation)}")
        assert blocking == [], "Level-A axe violations: " + "; ".join(
            format_axe_violation(v) for v in blocking
        )


def test_axe_scan_fails_on_known_level_a_witness(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector("dashboard-tabs [role='tab']")
        page.evaluate(
            """() => {
              const img = document.createElement('img');
              img.id = 'axe-red-witness';
              img.src = (
                'data:image/gif;base64,'
                + 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
              );
              document.body.prepend(img);
            }""",
        )
        blocking, _reported = run_axe_scan(page)
        assert blocking, "expected a Level-A violation for <img> without alt"


def test_rendered_live_dots_have_adjacent_text_labels(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector("live-dot .live-dot__label")
        assert_live_dots_have_text_labels(page)

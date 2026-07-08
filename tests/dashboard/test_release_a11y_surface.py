"""Terminal full-surface a11y release-gate scan (Story 5.22 AC1 / D1).

Closes the composite-scan gap the 5.11 rhythm fixture
(``editorial-scanning-rhythm.html``) leaves open: STOP banners (all
severities), the honest-disconnection banner + a disconnected resume card,
and the viewport degradation banner are composed onto ONE page
(``release-a11y-surface.html``) alongside the already-scanned rhythm surface
(masthead, KPI, resume, phase tracker, backlog tree, activity feed, tabs) and
scanned together, so cross-component landmark/heading-order issues a
per-component scan cannot see are caught by a single authoritative release
gate. This module does NOT re-test each component in isolation — the
per-component witnesses (``test_stop_banner_a11y.py``,
``test_connection_state_a11y.py``, ``test_viewport_banner_a11y.py``) own that.
"""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import (
    RELEASE_SURFACE_FIXTURE_PATH as _FIXTURE_PATH,
)
from dashboard._playwright_a11y import (
    assert_release_surface_complete,
    format_axe_violation,
    run_axe_scan,
    wait_for_release_surface_render,
    with_playwright_page,
)

pytestmark = [pytest.mark.integration]


def test_release_surface_zero_level_a_violations(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        wait_for_release_surface_render(page)
        blocking, reported = run_axe_scan(page)
        for violation in reported:
            print(f"AA-reported: {format_axe_violation(violation)}")
        assert blocking == [], "Level-A axe violations: " + "; ".join(
            format_axe_violation(v) for v in blocking
        )


def test_release_surface_covers_all_5c_gap_surfaces(
    running_dashboard: tuple[str, int, object],
) -> None:
    """D1: the composite must actually RENDER the 3 surfaces the 5.11 rhythm
    fixture omits -- a scan of an empty/incomplete page would vacuously pass.

    Asserts via the shared ``assert_release_surface_complete`` contract so this
    witness and the release-report script (which now calls the same helper)
    can't drift (Story 5.22 review P2)."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        wait_for_release_surface_render(page)
        assert_release_surface_complete(page)


def test_release_surface_fails_on_known_level_a_witness(
    running_dashboard: tuple[str, int, object],
) -> None:
    """D1: proves the scan actually catches a Level-A break (not vacuous)."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        wait_for_release_surface_render(page)
        page.evaluate(
            """() => {
              const img = document.createElement('img');
              img.id = 'axe-red-witness';
              img.src = (
                'data:image/gif;base64,'
                + 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
              );
              document.body.prepend(img);
            }"""
        )
        blocking, _reported = run_axe_scan(page)
        assert blocking, "expected a Level-A violation for <img> without alt"

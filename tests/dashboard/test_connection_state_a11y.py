"""Playwright a11y witness for honest disconnection (Story 5.20)."""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import with_playwright_page

pytestmark = [pytest.mark.integration]

_CONNECTION_FIXTURE = "/static/components/connection-state/connection-state.fixture.html"
_RESUME_FIXTURE = "/static/components/resume-card/resume-card.fixture.html"


def test_disconnection_banner_has_alert_role_and_text_copy(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_CONNECTION_FIXTURE}") as page:
        page.evaluate(
            """() => {
              window.__connectionFixture.reset();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
            }"""
        )
        banner = page.locator("#connection-banner-target .honest-disconnection-banner")
        assert banner.count() == 1
        assert banner.get_attribute("role") == "alert"
        detail = page.locator("#connection-banner-target .stop-banner__detail").inner_text()
        assert "Dashboard cannot reach state" in detail
        title = page.locator("#connection-banner-target .stop-banner__title").inner_text()
        assert "CRITICAL:" in title


def test_resume_card_disconnected_fixture_has_disabled_copy_and_stale_text(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_RESUME_FIXTURE}") as page:
        page.wait_for_selector("#resume-card-disconnected-target .resume-card--disconnected")
        button = page.locator("#resume-card-disconnected-target .copy-btn")
        assert button.get_attribute("aria-disabled") == "true"
        assert button.is_disabled()
        stale = page.locator("#resume-card-disconnected-target .resume-card__stale-warning")
        assert "may be stale" in stale.inner_text().lower()
        footer = page.locator(
            "#resume-card-disconnected-target freshness-footer .freshness-footer__timestamp"
        )
        assert "DISCONNECTED" in footer.inner_text()


def test_disconnection_banner_removed_on_recovery(
    running_dashboard: tuple[str, int, object],
) -> None:
    """DD-06 content-delta: the honest-disconnection banner appears only while
    disconnected and is removed on the next successful poll (not left stale)."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_CONNECTION_FIXTURE}") as page:
        page.evaluate(
            """() => {
              window.__connectionFixture.reset();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
            }"""
        )
        banner = page.locator("#connection-banner-target .honest-disconnection-banner")
        assert banner.count() == 1
        page.evaluate("() => window.__connectionFixture.simulateSuccess()")
        assert banner.count() == 0


def test_masthead_disconnected_live_dot_is_static_under_reduced_motion(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_CONNECTION_FIXTURE}") as page:
        page.emulate_media(reduced_motion="reduce")
        page.evaluate(
            """() => {
              window.__connectionFixture.reset();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
            }"""
        )
        dot = page.locator("#connection-masthead-target .live-dot__dot")
        class_name = dot.get_attribute("class") or ""
        assert "live-dot-pulse--stop" in class_name

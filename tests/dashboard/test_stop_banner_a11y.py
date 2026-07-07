"""Playwright a11y witness for STOP banners (Story 5.19)."""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import with_playwright_page

pytestmark = [pytest.mark.integration]

_FIXTURE_PATH = "/static/components/stop-banner/stop-banner.fixture.html"


def test_stop_banners_have_roles_and_text_severity_labels(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        page.wait_for_selector(".stop-banner")
        banners = page.locator(".stop-banner")
        count = banners.count()
        assert count == 7

        for index in range(count):
            banner = banners.nth(index)
            role = banner.get_attribute("role")
            assert role in {"alert", "status"}
            labelledby = banner.get_attribute("aria-labelledby")
            assert labelledby
            title = page.locator(f"#{labelledby}")
            title_text = title.inner_text()
            assert any(tag in title_text for tag in ("CRITICAL:", "WARNING:", "INFO:"))

        labels = page.locator(".stop-banner__title").all_inner_texts()
        assert any("CRITICAL:" in text for text in labels)
        assert any("WARNING:" in text for text in labels)
        assert any("INFO:" in text for text in labels)


def test_stop_banner_fixture_has_no_dialog_or_form(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        assert page.locator("dialog").count() == 0
        assert page.locator("form").count() == 0


def test_hostile_reason_renders_inert_text_not_markup(
    running_dashboard: tuple[str, int, object],
) -> None:
    """D4 / CR4.8-W3 behavioral witness (review 2026-07-07 P5): untrusted reason
    content renders as inert text (never markup/script), and sanitizeReason strips
    control chars, truncates, and coerces null."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            """async () => {
              const m = await import('/static/components/stop-banner/stop-banner.js');
              const host = document.createElement('div');
              document.body.appendChild(host);
              window.__xss = 0;
              m.renderStopBanners(host, [{
                triggerId: 'high_risk_path',
                targetId: 't',
                reason: '<img src=x onerror="window.__xss=1">',
                action: 'sdlc trace',
              }]);
              const ctrl = m.sanitizeReason(
                'a' + String.fromCharCode(0) + 'b' + String.fromCharCode(10) + 'c');
              const long = m.sanitizeReason('A'.repeat(5000));
              return {
                imgCount: host.querySelectorAll('img').length,
                xss: window.__xss,
                detailText: host.querySelector('.stop-banner__detail').textContent,
                ctrlHasNul: ctrl.indexOf(String.fromCharCode(0)) !== -1,
                ctrlHasNewline: ctrl.indexOf(String.fromCharCode(10)) !== -1,
                longLen: long.length,
                nullSanitized: m.sanitizeReason(null),
              };
            }"""
        )
        assert result["imgCount"] == 0
        assert result["xss"] == 0
        assert "onerror" in result["detailText"]  # preserved as inert text, not markup
        assert result["ctrlHasNul"] is False
        assert result["ctrlHasNewline"] is False
        assert result["longLen"] <= 201  # MAX_REASON_LEN (200) + ellipsis
        assert result["nullSanitized"] == ""


def test_empty_state_when_no_active_stops(
    running_dashboard: tuple[str, int, object],
) -> None:
    """AC3 behavioral witness (review 2026-07-07 P6): zero active STOPs -> exactly
    one empty-state with a freshness footer, zero banners."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            """async () => {
              const m = await import('/static/components/stop-banner/stop-banner.js');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.renderStopBanners(host, []);
              return {
                banners: host.querySelectorAll('.stop-banner').length,
                emptyMsg: host.querySelectorAll('.empty-state__message').length,
                hasEmptyClass: host.classList.contains('empty-state'),
                footer: host.querySelectorAll('freshness-footer').length,
              };
            }"""
        )
        assert result["banners"] == 0
        assert result["emptyMsg"] == 1
        assert result["hasEmptyClass"] is True
        assert result["footer"] == 1


def test_empty_state_falsy_message_renders_default_copy(
    running_dashboard: tuple[str, int, object],
) -> None:
    """DEF-5 behavioral witness (review 2026-07-07 P10): a falsy ('') message
    coerces to the anti-cynicism default copy at render time."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        text = page.evaluate(
            """async () => {
              const m = await import('/static/components/empty-state/empty-state.js');
              const host = document.createElement('div');
              m.renderEmptyState(host, { message: '' });
              return host.querySelector('.empty-state__message').textContent;
            }"""
        )
        assert text == "No STOPs in flight"


def test_unknown_trigger_renders_notice_tag_not_crit(
    running_dashboard: tuple[str, int, object],
) -> None:
    """Decision (a) behavioral witness (review 2026-07-07 P13): an unknown
    trigger_id renders a NOTICE: text tag with role=status, never crit."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            """async () => {
              const m = await import('/static/components/stop-banner/stop-banner.js');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.renderStopBanners(host, [{ triggerId: 'some_future_unknown_stop', targetId: 'x' }]);
              const banner = host.querySelector('.stop-banner');
              return {
                role: banner.getAttribute('role'),
                titleText: host.querySelector('.stop-banner__title').textContent,
                isCrit: banner.classList.contains('crit'),
              };
            }"""
        )
        assert result["role"] == "status"
        assert result["titleText"].startswith("NOTICE:")
        assert result["isCrit"] is False


def test_severity_dot_pulse_disabled_under_reduced_motion(
    running_dashboard: tuple[str, int, object],
) -> None:
    """DD-16 reduced-motion witness (review 2026-07-07 P9): the severity dot's
    pulse animation is disabled under prefers-reduced-motion: reduce."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        page.wait_for_selector(".stop-banner__severity-dot")
        page.emulate_media(reduced_motion="reduce")
        reduced = page.evaluate(
            "() => getComputedStyle(document.querySelector('.stop-banner__severity-dot'))"
            ".animationName"
        )
        assert reduced == "none"
        page.emulate_media(reduced_motion="no-preference")
        active = page.evaluate(
            "() => getComputedStyle(document.querySelector('.stop-banner__severity-dot'))"
            ".animationName"
        )
        assert active == "pulse"


def test_action_command_text_is_not_a_tab_stop(
    running_dashboard: tuple[str, int, object],
) -> None:
    """Keyboard-order witness (review 2026-07-07 P9): the display <code> is opted
    out of the tab sequence (tabindex=-1); the copy button stays reachable."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        page.wait_for_selector(".stop-banner")
        codes = page.locator(".inverted-command__text")
        assert codes.count() >= 1
        for index in range(codes.count()):
            assert codes.nth(index).get_attribute("tabindex") == "-1"
        buttons = page.locator(".copy-btn")
        assert buttons.count() >= 1
        for index in range(buttons.count()):
            tabindex = buttons.nth(index).get_attribute("tabindex")
            assert tabindex is None or int(tabindex) >= 0

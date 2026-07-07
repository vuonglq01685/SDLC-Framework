"""Integration tests for connection-state broker behavior (Story 5.20)."""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_FIXTURE_PATH = "/static/components/connection-state/connection-state.fixture.html"


@pytest.fixture()
def dashboard_base_url(tmp_path: Path) -> Generator[str, None, None]:
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}{_FIXTURE_PATH}", timeout=1) as resp:
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    yield base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@contextmanager
def _with_playwright_page(url: str) -> Iterator[object]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium not installed: {exc}")
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            yield page
        finally:
            browser.close()


def test_broker_does_not_flip_on_one_or_two_failures(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        result = page.evaluate(
            """async () => {
              window.__connectionFixture.reset();
              window.__connectionFixture.simulateFailure();
              const afterOne = window.__connectionFixture.getState();
              window.__connectionFixture.simulateFailure();
              const afterTwo = window.__connectionFixture.getState();
              return { afterOne, afterTwo };
            }"""
        )
    assert result["afterOne"] == "default"
    assert result["afterTwo"] == "default"


def test_broker_flips_on_three_failures_and_recovers_in_one_poll(
    dashboard_base_url: str,
) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        result = page.evaluate(
            """async () => {
              window.__connectionFixture.reset();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
              window.__connectionFixture.simulateFailure();
              const afterThree = window.__connectionFixture.getState();
              const subSel = '#connection-masthead-target .masthead__sub';
              const dotSel = '#connection-masthead-target live-dot';
              const bannerSel = '#connection-banner-target .stop-banner__detail';
              const subText = document.querySelector(subSel)?.textContent || '';
              const dotVariant = document.querySelector(dotSel)?.getAttribute('variant');
              const bannerText = document.querySelector(bannerSel)?.textContent || '';
              window.__connectionFixture.simulateSuccess();
              const afterRecover = window.__connectionFixture.getState();
              const dotAfter = document.querySelector(dotSel)?.getAttribute('variant');
              return { afterThree, afterRecover, subText, dotVariant, dotAfter, bannerText };
            }"""
        )
    assert result["afterThree"] == "disconnected"
    assert "DISCONNECTED" in result["subText"]
    assert result["dotVariant"] == "disconnected"
    assert "Dashboard cannot reach state" in result["bannerText"]
    assert result["afterRecover"] == "default"
    assert result["dotAfter"] == "default"


def test_aria_live_announces_enter_and_leave_disconnected(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        announcements = page.evaluate(
            """async () => {
              const masthead = await import('/static/components/masthead/masthead.js');
              const { createAriaLiveRateLimiter } = masthead;
              const times = [0, 90_000, 180_000];
              let idx = 0;
              const limiter = createAriaLiveRateLimiter({ now: () => times[idx++] });
              const out = [];
              out.push(limiter.onVariantChange('default'));
              out.push(limiter.onVariantChange('disconnected'));
              out.push(limiter.onVariantChange('default'));
              return out;
            }"""
        )
    assert announcements[1] == "Disconnected"
    assert announcements[2] == "Connected"


def test_aria_live_suppresses_within_rate_limit_window(dashboard_base_url: str) -> None:
    """AC2 / Story 5.6 suppress-without-advancing: a variant change INSIDE the 60s
    window returns no announcement, but the still-unannounced state is re-detected
    and announced on the next change once the window opens — a screen-reader user
    is never permanently starved of the current connection state."""
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        out = page.evaluate(
            """async () => {
              const masthead = await import('/static/components/masthead/masthead.js');
              const { createAriaLiveRateLimiter } = masthead;
              const times = [0, 30_000, 90_000];
              let idx = 0;
              const limiter = createAriaLiveRateLimiter({ now: () => times[idx++] });
              return [
                limiter.onVariantChange('default'),        // t=0   -> "Connected"
                limiter.onVariantChange('disconnected'),   // t=30s -> suppressed (< 60s)
                limiter.onVariantChange('disconnected'),   // t=90s -> "Disconnected"
              ];
            }"""
        )
    assert out[0] == "Connected"
    assert out[1] is None
    assert out[2] == "Disconnected"

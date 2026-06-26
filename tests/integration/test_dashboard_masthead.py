"""Integration tests for masthead + tab title automation (Story 5.6)."""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_FIXTURE_PATH = "/static/components/masthead/masthead.fixture.html"
_TAB_TITLE_TARGET = "#masthead-tab-title-target"
_DISCONNECTED_TARGET = "#masthead-disconnected-target"


@pytest.fixture()
def dashboard_base_url(tmp_path: Path) -> Generator[str, None, None]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    _write_state(
        state_dir / "state.json",
        project_name="SDLC-Framework",
        phase=2,
        progress=45,
    )
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


def _write_state(
    path: Path,
    *,
    project_name: str,
    phase: int,
    progress: int,
    connection_variant: str = "default",
) -> None:
    payload = {
        "project_name": project_name,
        "owner": "diep",
        "phase": phase,
        "progress": progress,
        "connection_variant": connection_variant,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


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


def test_format_tab_title_pure_formatter(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        result = page.evaluate(
            """async () => {
              const { formatTabTitle } = await import('/static/components/masthead/masthead.js');
              return formatTabTitle('SDLC-Framework', 2, 45);
            }"""
        )
    assert result == "SDLC-Framework \u00b7 Phase 2 45%"


def test_aria_live_rate_limiter_one_announcement_per_sixty_seconds(
    dashboard_base_url: str,
) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        announcements = page.evaluate(
            """async () => {
              const { createAriaLiveRateLimiter } = await import(
                '/static/components/masthead/masthead.js'
              );
              const times = [0, 30_000, 90_000];
              let idx = 0;
              const limiter = createAriaLiveRateLimiter({ now: () => times[idx++] });
              const out = [];
              out.push(limiter.onVariantChange('default'));
              out.push(limiter.onVariantChange('default'));
              out.push(limiter.onVariantChange('warn'));
              out.push(limiter.onVariantChange('disconnected'));
              return out;
            }"""
        )
    assert announcements[0] is not None
    assert announcements[1] is None
    assert announcements[2] is None
    assert announcements[3] is not None


def test_tab_title_updates_within_one_poll_cycle(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_function(
            """() => document.title === 'SDLC-Framework \u00b7 Phase 2 45%'""",
            timeout=5_000,
        )
        assert page.title() == "SDLC-Framework \u00b7 Phase 2 45%"


def test_masthead_disconnected_sub_line_uses_last_poll_timestamp(
    dashboard_base_url: str,
) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_DISCONNECTED_TARGET} .masthead__sub", timeout=5_000)
        sub_text = page.inner_text(f"{_DISCONNECTED_TARGET} .masthead__sub")
        assert "DISCONNECTED" in sub_text
        assert "LAST POLL" in sub_text
        assert "UPDATED" not in sub_text
        variant = page.get_attribute(f"{_DISCONNECTED_TARGET} live-dot", "variant")
        assert variant == "disconnected"


def test_masthead_banner_structure_and_typography(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_TAB_TITLE_TARGET} header[role='banner']", timeout=5_000)
        role = page.get_attribute(f"{_TAB_TITLE_TARGET} header[role='banner']", "role")
        assert role == "banner"
        h1_font = page.eval_on_selector(
            f"{_TAB_TITLE_TARGET} header h1",
            "el => getComputedStyle(el).fontFamily",
        )
        serif = page.eval_on_selector(
            ":root",
            "el => getComputedStyle(el).getPropertyValue('--font-serif').trim()",
        )
        assert serif
        assert serif.split(",")[0].strip('" ') in h1_font
        border = page.eval_on_selector(
            f"{_TAB_TITLE_TARGET} header",
            "el => getComputedStyle(el).borderBottomWidth",
        )
        assert border == "1px"
        live_region = page.get_attribute(
            f"{_TAB_TITLE_TARGET} .masthead__live-region",
            "aria-live",
        )
        assert live_region == "polite"

"""Integration tests for live-dot + freshness-footer (Story 5.5)."""

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

_FIXTURE_PATH = "/static/components/live-dot/live-dot.fixture.html"


@pytest.fixture()
def dashboard_base_url(tmp_path: Path) -> Generator[str, None, None]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
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
def _with_playwright_page(url: str, *, reduced_motion: bool) -> Iterator[object]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium not installed: {exc}")
        try:
            context = (
                browser.new_context(reduced_motion="reduce")
                if reduced_motion
                else browser.new_context()
            )
            page = context.new_page()
            if reduced_motion:
                page.emulate_media(reduced_motion="reduce")
            page.goto(url, wait_until="networkidle")
            yield page
        finally:
            browser.close()


def test_live_dot_pulse_active_without_reduced_motion(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url, reduced_motion=False) as page:
        animation_name = page.eval_on_selector(
            "#live-dot-reduced-motion-target .live-dot__dot",
            "el => getComputedStyle(el).animationName",
        )
        assert animation_name == "pulse"


def test_live_dot_reduced_motion_disables_pulse(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url, reduced_motion=True) as page:
        animation_name = page.eval_on_selector(
            "#live-dot-reduced-motion-target .live-dot__dot",
            "el => getComputedStyle(el).animationName",
        )
        assert animation_name in {"none", ""}


def test_freshness_footer_stale_timestamp_uses_ink_mute(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url, reduced_motion=False) as page:
        color = page.eval_on_selector(
            "#freshness-footer-stale .freshness-footer__timestamp",
            "el => getComputedStyle(el).color",
        )
        ink_mute = page.eval_on_selector(
            ":root",
            "el => getComputedStyle(el).getPropertyValue('--ink-mute').trim()",
        )
        assert color not in {"", "rgb(0, 0, 0)"}
        assert ink_mute
        assert color == page.evaluate(
            """(inkMute) => {
              const probe = document.createElement('span');
              probe.style.color = inkMute;
              document.body.appendChild(probe);
              const resolved = getComputedStyle(probe).color;
              probe.remove();
              return resolved;
            }""",
            ink_mute,
        )


def test_freshness_footer_fresh_timestamp_uses_ink(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url, reduced_motion=False) as page:
        has_fresh_class = page.eval_on_selector(
            "#footer-fresh-mount .freshness-footer__timestamp",
            "el => el.classList.contains('freshness-footer__timestamp--fresh')",
        )
        assert has_fresh_class is True

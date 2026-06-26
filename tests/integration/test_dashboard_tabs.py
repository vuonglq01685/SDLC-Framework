"""Playwright integration tests for tabs WAI-ARIA keyboard (Story 5.11 AC1)."""

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

_FIXTURE_PATH = "/static/components/tabs/tabs.fixture.html"
_TABS_HOST = "#tabs-keyboard-target"
_TABLIST = f"{_TABS_HOST} [role='tablist']"
_TABS = f"{_TABLIST} [role='tab']"
_FIRST_TAB = f"{_TABS}:first-of-type"
_SECOND_TAB = f"{_TABS}:nth-of-type(2)"


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
            page.wait_for_selector(_FIRST_TAB)
            yield page
        finally:
            browser.close()


def test_arrow_right_moves_focus_without_dropping_to_body(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_FIRST_TAB).focus()
        first_id = page.eval_on_selector(_FIRST_TAB, "el => el.id")
        page.keyboard.press("ArrowRight")
        active = page.evaluate("() => document.activeElement && document.activeElement.id")
        assert active != first_id
        assert active and active != "body"


def test_home_end_jump_to_first_and_last_tab(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_SECOND_TAB).focus()
        page.keyboard.press("End")
        last_id = page.eval_on_selector(f"{_TABS}:last-of-type", "el => el.id")
        active = page.evaluate("() => document.activeElement && document.activeElement.id")
        assert active == last_id
        page.keyboard.press("Home")
        first_id = page.eval_on_selector(_FIRST_TAB, "el => el.id")
        active = page.evaluate("() => document.activeElement && document.activeElement.id")
        assert active == first_id


def test_enter_activates_tab_and_reveals_panel(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_SECOND_TAB).focus()
        panel_id = page.get_attribute(_SECOND_TAB, "aria-controls")
        assert panel_id
        page.keyboard.press("Enter")
        selected = page.get_attribute(_SECOND_TAB, "aria-selected")
        assert selected == "true"
        hidden = page.get_attribute(f"#{panel_id}", "hidden")
        assert hidden is None


def test_space_activates_tab(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_SECOND_TAB).focus()
        page.keyboard.press("Space")
        selected = page.get_attribute(_SECOND_TAB, "aria-selected")
        assert selected == "true"


def test_exactly_one_tab_has_tabindex_zero(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        count = page.evaluate(
            """() => document.querySelectorAll(
                "#tabs-keyboard-target [role='tab'][tabindex='0']"
            ).length""",
        )
        assert count == 1

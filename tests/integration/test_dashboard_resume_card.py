"""Integration tests for resume card copy + greeting (Story 5.8)."""

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

_FIXTURE_PATH = "/static/components/resume-card/resume-card.fixture.html"
_COPY_TARGET = "#resume-card-copy-target"
_GREETING_TARGET = "#resume-card-greeting-target"
_SUBSEQUENT_TARGET = "#resume-card-subsequent-target"


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


def test_normalize_command_pure_function(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        result = page.evaluate(
            """async () => {
              const { normalizeCommand } = await import(
                '/static/components/resume-card/resume-card.js'
              );
              return {
                trimmed: normalizeCommand('  sdlc status  \\n\\n'),
                strippedPrefix: normalizeCommand('$ sdlc status'),
              };
            }"""
        )
    assert result["trimmed"] == "sdlc status"
    assert result["strippedPrefix"] == "sdlc status"


def test_greeting_shown_once_per_session(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_GREETING_TARGET} .resume-card__greeting", timeout=5_000)
        first = page.inner_text(f"{_GREETING_TARGET} .resume-card__greeting")
        assert first == "Welcome, diep."
        page.evaluate(
            """() => {
              const el = document.querySelector('#resume-card-greeting-target');
              el.setAttribute('variant', 'default');
            }"""
        )
        assert page.query_selector(f"{_GREETING_TARGET} .resume-card__greeting") is None


def test_subsequent_session_omits_greeting(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.add_init_script(
            """() => {
              sessionStorage.setItem('sdlc.resume-card.greetingShown', '1');
            }"""
        )
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(_SUBSEQUENT_TARGET, timeout=5_000)
        assert page.query_selector(f"{_SUBSEQUENT_TARGET} .resume-card__greeting") is None
        assert "YOU ARE HERE" in page.inner_text(_SUBSEQUENT_TARGET).upper()


def test_copy_button_writes_clipboard_and_swaps_icon(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_COPY_TARGET} .copy-btn", timeout=5_000)
        page.evaluate(
            """() => {
              window.__copied = null;
              navigator.clipboard.writeText = async (text) => {
                window.__copied = text;
              };
            }"""
        )
        page.click(f"{_COPY_TARGET} .copy-btn")
        copied = page.evaluate("() => window.__copied")
        assert copied == "sdlc status --suggested-next"
        href_after_click = page.get_attribute(f"{_COPY_TARGET} .copy-btn use", "href")
        assert href_after_click is not None and href_after_click.endswith("#check")
        live_text = page.inner_text(f"{_COPY_TARGET} .resume-card__live-region")
        assert live_text.strip().lower() == "copied to clipboard"
        page.wait_for_function(
            """() => {
              const href = document
                .querySelector('#resume-card-copy-target .copy-btn use')
                ?.getAttribute('href');
              return href != null && href.endsWith('#copy');
            }""",
            timeout=2_500,
        )


def test_copy_button_focus_ring_keyboard_vs_mouse(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_COPY_TARGET} .copy-btn", timeout=5_000)
        page.click(f"{_COPY_TARGET} .copy-btn")
        mouse_focus_visible = page.evaluate(
            """() => {
              const btn = document.querySelector('#resume-card-copy-target .copy-btn');
              return btn != null && btn.matches(':focus-visible');
            }"""
        )
        assert mouse_focus_visible is False
        page.evaluate("() => document.activeElement?.blur()")
        for _ in range(6):
            page.keyboard.press("Tab")
            if page.evaluate(
                """() => {
                  const btn = document.querySelector('#resume-card-copy-target .copy-btn');
                  return document.activeElement === btn;
                }"""
            ):
                break
        keyboard_focus_visible = page.evaluate(
            """() => {
              const btn = document.querySelector('#resume-card-copy-target .copy-btn');
              return btn != null && btn.matches(':focus-visible');
            }"""
        )
        assert keyboard_focus_visible is True
        keyboard_shadow = page.eval_on_selector(
            f"{_COPY_TARGET} .copy-btn",
            "el => getComputedStyle(el).boxShadow",
        )
        assert keyboard_shadow not in ("none", "")


def test_command_code_is_not_a_keyboard_tab_stop(dashboard_base_url: str) -> None:
    """Regression (5.18 fix): DEF-4 gave `.inverted-command__text` `overflow-x:
    auto`, which in Chromium 130+ (keyboard-focusable scrollers) turns the
    non-interactive command <code> into a Tab stop. That both pollutes the tab
    order (a11y) and pushes the copy button past the 6-Tab window
    `test_copy_button_focus_ring_keyboard_vs_mouse` relies on. The <code> must
    carry tabindex="-1" so it stays out of sequential focus while keeping
    pointer scroll. Guards against a refactor silently dropping the attribute.
    """
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_COPY_TARGET} .inverted-command__text", timeout=5_000)
        tabindex = page.get_attribute(f"{_COPY_TARGET} .inverted-command__text", "tabindex")
        assert tabindex == "-1"


def test_resume_card_region_and_inverted_surface_tokens(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.wait_for_selector(f"{_COPY_TARGET} .resume-card", timeout=5_000)
        role = page.get_attribute(f"{_COPY_TARGET} .resume-card", "role")
        assert role == "region"
        bg = page.eval_on_selector(
            f"{_COPY_TARGET} .inverted-command",
            "el => getComputedStyle(el).backgroundColor",
        )
        ink = page.eval_on_selector(
            ":root",
            "el => getComputedStyle(el).getPropertyValue('--ink').trim()",
        )
        assert ink
        assert bg != "rgba(0, 0, 0, 0)"

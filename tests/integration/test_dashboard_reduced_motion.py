"""Reduced-motion integration test (Story 5.4 AC3 / DD-16)."""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_FIXTURE_PATH = "/static/fixtures/reduced-motion-pulse.html"


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


def _pulse_animation_name(url: str, *, reduced_motion: bool) -> str:
    """Computed ``animation-name`` of the fixture dot.

    Skips gracefully if the Playwright browser binary is not installed — CI runs
    ``playwright install`` but a bare local ``pytest`` may not, and
    ``importorskip`` only guards the Python package, not the browser binary.
    """
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:  # e.g. "Executable doesn't exist"
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
            return page.eval_on_selector(
                "#pulse-fixture",
                "el => getComputedStyle(el).animationName",
            )
        finally:
            browser.close()


def test_pulse_animation_active_without_reduced_motion(dashboard_base_url: str) -> None:
    # Positive control: without reduced motion the pulse MUST run. This keeps the
    # negative assertion below from passing vacuously if the base `.live-dot-pulse`
    # rule or `@keyframes pulse` were ever removed.
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    assert _pulse_animation_name(url, reduced_motion=False) == "pulse"


def test_reduced_motion_disables_pulse_animation(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    assert _pulse_animation_name(url, reduced_motion=True) in {"none", ""}

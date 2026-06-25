"""Playwright integration tests for backlog tree keyboard + focus ring (Story 5.10).

Closes Story 5.4 DEF-6: `.tree-expander` shows the DD-15 focus ring on
`:focus-visible` and suppresses it for mouse-only `:focus`.
"""

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

_FIXTURE_PATH = "/static/components/backlog-tree/backlog-tree.fixture.html"
_TREE = "#backlog-tree-keyboard-target"
_EPIC_EXPANDER = f"{_TREE} .tree-epic-head .tree-expander"
# aria-expanded lives on the role="treeitem" wrapper, not the inner button (PAT-6).
_EPIC_TREEITEM = f"{_TREE} .tree-epic"


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
            page.wait_for_selector(_EPIC_EXPANDER)
            yield page
        finally:
            browser.close()


def _box_shadow(page: object, selector: str) -> str:
    return page.eval_on_selector(
        selector,
        "el => getComputedStyle(el).boxShadow",
    )


def test_arrow_down_moves_focus_to_next_visible_row(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_EPIC_EXPANDER).focus()
        first_id = page.eval_on_selector(_EPIC_EXPANDER, "el => el.dataset.nodeId")
        page.keyboard.press("ArrowDown")
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.dataset.nodeId",
        )
        assert active_id != first_id
        assert active_id


def test_arrow_down_reaches_task_row_keyboard_focus(dashboard_base_url: str) -> None:
    """AC1 / DEC-1 regression: arrow keys must navigate onto TASK rows.

    The leaf (task) expander must stay keyboard-focusable — if it is
    ``visibility:hidden`` it is non-focusable and ``.focus()`` silently drops
    to ``<body>``, stranding the user at the first story.
    """
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_EPIC_EXPANDER).focus()
        page.keyboard.press("ArrowDown")  # epic -> story EPIC-stripe-S04
        page.keyboard.press("ArrowDown")  # story -> task EPIC-stripe-S04-T01
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.dataset.nodeId",
        )
        assert active_id == "EPIC-stripe-S04-T01", (
            f"keyboard focus must land on the task row, got {active_id!r}"
        )


def test_enter_toggles_aria_expanded_on_parent(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_EPIC_EXPANDER).focus()
        before = page.get_attribute(_EPIC_TREEITEM, "aria-expanded")
        page.keyboard.press("Enter")
        after = page.get_attribute(_EPIC_TREEITEM, "aria-expanded")
        assert before == "true"
        assert after == "false"


def test_keyboard_focus_shows_focus_visible_ring(dashboard_base_url: str) -> None:
    """DEF-6: keyboard focus uses the DD-15 2px rule-strong ring on .tree-expander."""
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_EPIC_EXPANDER).focus()
        shadow = _box_shadow(page, _EPIC_EXPANDER)
        assert shadow not in {"", "none"}


def test_mouse_click_suppresses_focus_ring(dashboard_base_url: str) -> None:
    """DEF-6: mouse focus must not paint the focus-visible ring."""
    url = f"{dashboard_base_url}{_FIXTURE_PATH}"
    with _with_playwright_page(url) as page:
        page.locator(_EPIC_EXPANDER).click()
        shadow = _box_shadow(page, _EPIC_EXPANDER)
        assert shadow in {"", "none"}

"""Keyboard-only navigation tests on the dashboard composite fixture (Story 5.12 AC3)."""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import with_playwright_page

pytestmark = [pytest.mark.integration]

_TABS = "dashboard-tabs [role='tab']"
_TREE_EXPANDER = "backlog-tree .tree-expander"
_COPY_BTN = "resume-card .copy-btn"


def _box_shadow(page: object, selector: str) -> str:
    return page.eval_on_selector(selector, "el => getComputedStyle(el).boxShadow")


_INTERACTIVE_WIDGETS = {
    "tablist": _TABS,
    "backlog-tree": _TREE_EXPANDER,
    "copy-button": _COPY_BTN,
}


def _active_matches(page: object, selector: str) -> bool:
    return page.evaluate(
        "(sel) => !!document.activeElement && document.activeElement.matches(sel)",
        selector,
    )


def test_tab_reaches_all_interactive_widgets(dashboard_composite_url: str) -> None:
    # Tabs and backlog-tree use roving tabindex: each composite widget exposes
    # exactly ONE Tab stop (intra-widget movement is via Arrow/Home/End, covered
    # by the sibling tests). So assert Tab reaches each widget, not every element.
    with with_playwright_page(dashboard_composite_url) as page:
        for selector in _INTERACTIVE_WIDGETS.values():
            page.wait_for_selector(selector)

        reached: set[str] = set()
        for _ in range(40):
            for name, selector in _INTERACTIVE_WIDGETS.items():
                if _active_matches(page, selector):
                    reached.add(name)
            if reached == set(_INTERACTIVE_WIDGETS):
                break
            page.keyboard.press("Tab")

        assert reached == set(_INTERACTIVE_WIDGETS), (
            f"Tab must reach each interactive widget; reached={reached!r}"
        )


def test_keyboard_focus_shows_dd15_focus_ring(dashboard_composite_url: str) -> None:
    # DD-15 ring is :focus-visible only; a programmatic .focus() does not reliably
    # match :focus-visible, so drive the copy button with the keyboard and assert
    # the ring APPEARS relative to the unfocused state.
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector(_COPY_BTN)
        unfocused = _box_shadow(page, _COPY_BTN)

        reached = False
        for _ in range(40):
            page.keyboard.press("Tab")
            if _active_matches(page, _COPY_BTN):
                reached = True
                break
        assert reached, "copy button must be reachable by Tab"

        focused = _box_shadow(page, _COPY_BTN)
        assert focused not in {"", "none"}, f"DD-15 focus ring missing: {focused!r}"
        assert focused != unfocused, "DD-15 ring must appear on keyboard focus"


def test_backlog_tree_arrow_down_reaches_task_row(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector(_TREE_EXPANDER)
        page.locator(_TREE_EXPANDER).first.focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.dataset.nodeId",
        )
        assert active_id and "T01" in active_id, (
            f"ArrowDown must reach a task row, got {active_id!r}"
        )


def test_tabs_arrow_right_moves_focus(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector(_TABS)
        first_tab = page.locator(_TABS).first
        first_tab.focus()
        first_id = first_tab.get_attribute("id")
        page.keyboard.press("ArrowRight")
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.id",
        )
        assert active_id != first_id
        assert active_id


def test_tabs_home_end_jump(dashboard_composite_url: str) -> None:
    with with_playwright_page(dashboard_composite_url) as page:
        page.wait_for_selector(_TABS)
        tabs = page.locator(_TABS)
        tabs.last.focus()
        page.keyboard.press("Home")
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.id",
        )
        assert active_id == tabs.first.get_attribute("id")
        page.keyboard.press("End")
        active_id = page.evaluate(
            "() => document.activeElement && document.activeElement.id",
        )
        assert active_id == tabs.last.get_attribute("id")

"""Playwright behavioral contracts for the Activity Feed + Empty State (Story 5.11).

These execute the real components in a browser DOM (unlike the static-source greps in
``tests/unit/dashboard/test_tabs_activity_feed_fixture.py``) so they actually MEASURE
AC2 ("entries bounded to last 50, older entries scroll out", incremental prepend) and
AC3/UX-DR15 ("empty state must never be silently blank"). Added by code review of
Story 5.11 as the RED->GREEN witness for the feed render-order/eviction defect.
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

_FEED_FIXTURE = "/static/components/activity-feed/activity-feed.fixture.html"
_EMPTY_FIXTURE = "/static/components/empty-state/empty-state.fixture.html"
_FEED_ROWS = "#activity-feed-target .activity-feed__entry"
_EMPTY_MESSAGE = "#empty-state-target .empty-state__message"


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
            with urllib.request.urlopen(f"{base_url}{_FEED_FIXTURE}", timeout=1) as resp:
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
def _with_playwright_page(url: str, ready_selector: str) -> Iterator[object]:
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
            page.wait_for_selector(ready_selector)
            yield page
        finally:
            browser.close()


def test_activity_feed_renders_exactly_fifty_entries(dashboard_base_url: str) -> None:
    url = f"{dashboard_base_url}{_FEED_FIXTURE}"
    with _with_playwright_page(url, _FEED_ROWS) as page:
        count = page.evaluate(f"() => document.querySelectorAll({_FEED_ROWS!r}).length")
        assert count == 50


def test_activity_feed_renders_newest_entry_on_top(dashboard_base_url: str) -> None:
    """AC2 / §6.8: new entries prepend -> the newest run is at the TOP, oldest at the bottom."""
    url = f"{dashboard_base_url}{_FEED_FIXTURE}"
    with _with_playwright_page(url, _FEED_ROWS) as page:
        data = page.evaluate(
            f"""() => {{
                const rows = [...document.querySelectorAll({_FEED_ROWS!r})];
                return {{
                    ids: rows.map((r) => r.dataset.entryId),
                    stamps: rows.map(
                        (r) => r.querySelector('.activity-feed__timestamp').textContent,
                    ),
                }};
            }}"""
        )
        stamps = data["stamps"]
        assert stamps == sorted(stamps, reverse=True), "feed must render newest entry on top"
        assert data["ids"][0] == "run-050", "top row must be the newest synthetic run"
        assert data["ids"][-1] == "run-001", "bottom row must be the oldest synthetic run"


def test_activity_feed_poll_prepends_newest_and_evicts_oldest(dashboard_base_url: str) -> None:
    """AC2: a poll prepends the newest entry, stays bounded to 50, and the OLDEST scrolls out."""
    url = f"{dashboard_base_url}{_FEED_FIXTURE}"
    with _with_playwright_page(url, _FEED_ROWS) as page:
        # Tag every existing row so we can prove the render is incremental (no full re-render).
        page.evaluate(
            f"""() => document.querySelectorAll({_FEED_ROWS!r})
                .forEach((r) => {{ r.dataset.witness = 'keep'; }})"""
        )
        page.evaluate(
            """async () => {
                const mod = await import('/static/components/activity-feed/activity-feed.js');
                const host = document.getElementById('activity-feed-target');
                mod.prependActivityFeedEntry(host, {
                    id: 'run-new',
                    timestamp: '2026-06-26T11:00:00',
                    agentName: 'dev-story',
                    targetId: '5-11',
                    outcome: 'approved',
                    duration: '1m 0s',
                });
            }"""
        )
        after = page.evaluate(
            f"""() => {{
                const rows = [...document.querySelectorAll({_FEED_ROWS!r})];
                return {{
                    count: rows.length,
                    topId: rows[0].dataset.entryId,
                    ids: rows.map((r) => r.dataset.entryId),
                    freshlyCreated: rows
                        .filter((r) => r.dataset.witness !== 'keep')
                        .map((r) => r.dataset.entryId),
                }};
            }}"""
        )
        assert after["count"] == 50, "feed stays bounded to the last 50 after a poll"
        assert after["topId"] == "run-new", "the newest entry prepends to the top"
        assert "run-050" in after["ids"], "the newest historical run must NOT be evicted"
        assert "run-001" not in after["ids"], "the oldest run must scroll out (AC2)"
        assert after["freshlyCreated"] == ["run-new"], (
            "only the new row is created; existing nodes preserved"
        )


def test_empty_state_renders_non_blank_message_and_footer(dashboard_base_url: str) -> None:
    """AC3 / UX-DR15: empty state renders a non-blank anti-cynicism message + footer."""
    url = f"{dashboard_base_url}{_EMPTY_FIXTURE}"
    with _with_playwright_page(url, _EMPTY_MESSAGE) as page:
        data = page.evaluate(
            """() => {
                const host = document.getElementById('empty-state-target');
                const msg = host.querySelector('.empty-state__message');
                return {
                    message: msg ? msg.textContent.trim() : null,
                    hasFooter: !!host.querySelector('freshness-footer'),
                };
            }"""
        )
        assert data["message"], (
            "empty state must render a non-blank message (UX-DR15: no silent blank)"
        )
        assert "All clear!" not in data["message"], "D2 bans the exclamatory 'All clear!' form"
        assert data["hasFooter"], "empty state must include the freshness footer (AC3)"

"""Playwright behavioral contracts for the Backlog Tree real-hierarchy poller (Story 5.15).

Executes the real `/api/backlog` route + `backlog-tree-live.js` poller in a
browser DOM (mirrors `test_dashboard_phase_tracker_live.py`) — the
static-source contract in `test_backlog_tree_live_source.py` cannot MEASURE
actual rendered DOM state, canonical-id text content, or URL-hash behavior
across a reload.

Covers:
  AC   — hierarchy renders from the real Epic->Story->Task artifact tree
         (D1/D2), task ids in inline code are canonical (Task 3).
  D3   — clicking a node expands/collapses AND persists the expanded-id set
         to the URL hash; a reload of the shared-hash URL reproduces the
         same expansion (AC "state persists in URL hash for shareability").
  D4   — an empty (zero-epic) real backlog still exposes a Tab-reachable
         entry point (DEF-3).
  D5   — an unknown flow step renders a fallback pill, never a silent drop
         (DEF-5), exercised directly against `pills.js` (no persisted real
         epic `flow` field exists yet -- see Dev Notes).
"""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.cli._epic_story_models import (
    _EpicEntry,
    _StoryEntry,
    _TaskEntry,
    serialize_entry,
    serialize_task_entry,
)
from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_LIVE_FIXTURE = "/static/components/backlog-tree/backlog-tree-live.fixture.html"
_TREE = "#backlog-tree-live-target"
_DRAFTED_AT = "2026-07-01T00:00:00.000Z"
_EPICS_DIR = "01-Requirement/04-Epics"
_STORIES_DIR = "01-Requirement/05-Stories"
_TASKS_DIR = "03-Implementation/tasks"


def _write_epic(root: Path, *, id_: str, label: str, ordering: int = 0) -> None:
    entry = _EpicEntry(
        id=id_,
        label=label,
        priority="P1",
        ordering=ordering,
        acceptance_criteria=("Criterion 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="epic-generator",
    )
    path = root / _EPICS_DIR / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_story(root: Path, *, id_: str, epic_id: str, seq: int, label: str) -> None:
    entry = _StoryEntry(
        id=id_,
        epic_id=epic_id,
        seq=seq,
        label=label,
        as_a="a user",
        i_want="a thing",
        so_that="value",
        given_when_then=("Given/When/Then 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="story-writer",
    )
    path = root / _STORIES_DIR / epic_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_task(root: Path, *, id_: str, story_id: str, label: str, stage: str = "pending") -> None:
    entry = _TaskEntry(id=id_, story_id=story_id, label=label, stage=stage)
    path = root / _TASKS_DIR / story_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_task_entry(entry), encoding="utf-8")


def _write_real_hierarchy(root: Path) -> None:
    _write_epic(root, id_="EPIC-stripe-webhook", label="Stripe webhook pipeline")
    _write_story(
        root,
        id_="EPIC-stripe-webhook-S04-idempotency",
        epic_id="EPIC-stripe-webhook",
        seq=4,
        label="Idempotency handling",
    )
    _write_task(
        root,
        id_="EPIC-stripe-webhook-S04-idempotency-T01-redis-key",
        story_id="EPIC-stripe-webhook-S04-idempotency",
        label="Redis key design",
        stage="done",
    )
    _write_task(
        root,
        id_="EPIC-stripe-webhook-S04-idempotency-T02-handler",
        story_id="EPIC-stripe-webhook-S04-idempotency",
        label="Handler integration",
        stage="pending",
    )


@contextmanager
def _dashboard(tmp_path: Path, *, fixture: str = _LIVE_FIXTURE) -> Iterator[str]:
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}{fixture}", timeout=1) as resp:
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def dashboard_base_url(tmp_path: Path) -> Generator[str, None, None]:
    _write_real_hierarchy(tmp_path)
    with _dashboard(tmp_path) as base_url:
        yield base_url


@pytest.fixture()
def empty_dashboard_base_url(tmp_path: Path) -> Generator[str, None, None]:
    with _dashboard(tmp_path) as base_url:
        yield base_url


@contextmanager
def _with_playwright_page(url: str, *, wait_for: str) -> Iterator[object]:
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
            page.wait_for_selector(wait_for, timeout=5_000)
            yield page
        finally:
            browser.close()


class TestRealHierarchyRendering:
    def test_renders_real_epic_story_task_with_canonical_inline_code_ids(
        self, dashboard_base_url: str
    ) -> None:
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            epic_code = page.inner_text(f"{_TREE} .tree-epic-head code.inline-code")
            assert epic_code == "EPIC-stripe-webhook"

            # Expand the epic to reveal the story/task inline-code ids.
            page.click(f"{_TREE} .tree-epic-head .tree-expander")
            story_code = page.inner_text(f"{_TREE} .tree-story-head code.inline-code")
            assert story_code == "EPIC-stripe-webhook-S04-idempotency"

            task_code = page.inner_text(f"{_TREE} .tree-task__meta code.inline-code")
            assert task_code == "EPIC-stripe-webhook-S04-idempotency-T01-redis-key"


class TestUrlHashPersistence:
    def test_expanding_a_node_writes_its_canonical_id_to_the_hash(
        self, dashboard_base_url: str
    ) -> None:
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            page.click(f"{_TREE} .tree-epic-head .tree-expander")
            page.wait_for_function(
                "() => window.location.hash.includes('EPIC-stripe-webhook')",
                timeout=5_000,
            )
            assert "backlog=EPIC-stripe-webhook" in page.evaluate("() => window.location.hash")

    def test_reload_with_shared_hash_reproduces_the_same_expansion(
        self, dashboard_base_url: str
    ) -> None:
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            page.click(f"{_TREE} .tree-epic-head .tree-expander")
            page.wait_for_function(
                "() => window.location.hash.includes('EPIC-stripe-webhook')",
                timeout=5_000,
            )
            shared_hash = page.evaluate("() => window.location.hash")

        # Simulate opening the shared link fresh (RED against the 5.10
        # no-persistence baseline: a fresh load never starts pre-expanded).
        shared_url = f"{url}{shared_hash}"
        with _with_playwright_page(shared_url, wait_for=f"{_TREE} .tree-epic") as page:
            page.wait_for_function(
                f"""() => document
                    .querySelector({_TREE + " .tree-epic"!r})
                    .getAttribute('aria-expanded') === 'true'""",
                timeout=5_000,
            )
            expanded = page.get_attribute(f"{_TREE} .tree-epic", "aria-expanded")
            assert expanded == "true"

    def test_collapsing_removes_the_id_from_the_hash(self, dashboard_base_url: str) -> None:
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            page.click(f"{_TREE} .tree-epic-head .tree-expander")
            page.wait_for_function(
                "() => window.location.hash.includes('EPIC-stripe-webhook')",
                timeout=5_000,
            )
            page.click(f"{_TREE} .tree-epic-head .tree-expander")
            page.wait_for_function(
                "() => !window.location.hash.includes('EPIC-stripe-webhook')",
                timeout=5_000,
            )

    def test_malformed_hash_id_is_silently_ignored_not_thrown(
        self, dashboard_base_url: str
    ) -> None:
        """D3 injection-safety: a non-canonical hash value must not crash the page."""
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}#backlog=<script>alert(1)</script>,not-canonical"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            expanded = page.get_attribute(f"{_TREE} .tree-epic", "aria-expanded")
            # Unknown/malformed ids are dropped -- falls back to the default
            # (server-emitted, fully-collapsed) render, never a thrown error.
            assert expanded == "false"


class TestEmptyBacklogTabReachability:
    def test_zero_epic_backlog_renders_a_tab_reachable_empty_state(
        self, empty_dashboard_base_url: str
    ) -> None:
        url = f"{empty_dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .backlog-tree__empty") as page:
            text = page.inner_text(f"{_TREE} .backlog-tree__empty")
            assert text.strip()
            tab_index = page.eval_on_selector(f"{_TREE} .backlog-tree__empty", "el => el.tabIndex")
            assert tab_index == 0


class TestUnknownFlowStepFallbackPill:
    def test_unknown_flow_step_renders_a_fallback_pill_not_a_silent_drop(
        self, dashboard_base_url: str
    ) -> None:
        url = f"{dashboard_base_url}{_LIVE_FIXTURE}"
        with _with_playwright_page(url, wait_for=f"{_TREE} .tree-epic") as page:
            result = page.evaluate(
                """async () => {
                    const mod = await import('/static/components/pills/pills.js');
                    const group = mod.createFlowPillGroup(['research', 'totally-unknown-stage']);
                    document.body.appendChild(group);
                    const labels = [...group.querySelectorAll('.pill')].map(
                        (el) => el.textContent
                    );
                    group.remove();
                    return labels;
                }"""
            )
            assert result == ["research", "totally-unknown-stage"], (
                "unknown flow step must render a fallback pill, not be dropped (DEF-5)"
            )

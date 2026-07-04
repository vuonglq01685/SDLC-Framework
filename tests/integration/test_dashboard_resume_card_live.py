"""Playwright behavioral contracts for the Resume Card real-data path (Story 5.18).

Mirrors ``test_dashboard_activity_feed_live.py`` / ``test_dashboard_backlog_tree_live.py``:
exercises the real ``/api/resume`` route + the live poller in a browser DOM, proving
AC1 (real breadcrumb/suggested-next-command, matching ``sdlc status``), AC2 (a state
change + poll updates the card within one poll cycle and the copy button reads the
NEW command), and the Task 4/6 hardening (in-flight guard, AbortController-on-
disconnect, DEF-3 loading state, DEF-5 change-only announcement, DEF-8 render
coalescing, D5 interior-newline hardening).
"""

from __future__ import annotations

import json
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

_LIVE_FIXTURE = "/static/components/resume-card/resume-card-live.fixture.html"
_TARGET = "#resume-card-live-target"
_DRAFTED_AT = "2026-07-01T00:00:00.000Z"
_EPICS_DIR = "01-Requirement/04-Epics"
_STORIES_DIR = "01-Requirement/05-Stories"
_TASKS_DIR = "03-Implementation/tasks"


def _write_state(repo_root: Path, *, phase: int = 1, epics: dict | None = None) -> None:
    state_dir = repo_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "next_monotonic_seq": 0,
        "phase": phase,
        "epics": epics or {},
        "stories": {},
        "tasks": {},
        "auto_loop_status": "idle",
        "stop_reason": None,
    }
    (state_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_epic(root: Path, *, id_: str, label: str) -> None:
    entry = _EpicEntry(
        id=id_,
        label=label,
        priority="P1",
        ordering=0,
        acceptance_criteria=("Criterion 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="epic-generator",
    )
    path = root / _EPICS_DIR / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_story(root: Path, *, id_: str, epic_id: str, label: str) -> None:
    entry = _StoryEntry(
        id=id_,
        epic_id=epic_id,
        seq=1,
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


def _write_task(root: Path, *, id_: str, story_id: str, label: str, stage: str) -> None:
    entry = _TaskEntry(id=id_, story_id=story_id, label=label, stage=stage)
    path = root / _TASKS_DIR / story_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_task_entry(entry), encoding="utf-8")


@pytest.fixture()
def dashboard_repo(tmp_path: Path) -> Generator[tuple[str, Path], None, None]:
    _write_state(tmp_path, phase=1, epics={})
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/resume", timeout=1) as resp:
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    yield base_url, tmp_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def _browser() -> Generator[object, None, None]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium not installed: {exc}")
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def _with_playwright_page(
    browser: object, url: str, ready_selector: str, *, wait_until: str = "load"
) -> Iterator[object]:
    page = browser.new_page()  # type: ignore[attr-defined]
    try:
        # The live fixture polls /api/resume every ~100-200ms in these tests --
        # network is never idle, so "networkidle" would hang.
        page.goto(url, wait_until=wait_until)
        page.wait_for_selector(ready_selector)
        yield page
    finally:
        page.close()


def test_resume_card_live_renders_real_breadcrumb_matching_cli_status(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """AC1: real breadcrumb/suggested-next-command, and the suggested command is
    the SAME one `sdlc status` would print for the same state (D2 single source)."""
    base_url, repo_root = dashboard_repo
    _write_state(repo_root, phase=3, epics={"epic-1": {}})
    _write_epic(repo_root, id_="EPIC-stripe-webhook", label="Stripe webhook")
    _write_story(
        repo_root,
        id_="EPIC-stripe-webhook-S01-setup",
        epic_id="EPIC-stripe-webhook",
        label="Setup",
    )
    _write_task(
        repo_root,
        id_="EPIC-stripe-webhook-S01-setup-T01-init",
        story_id="EPIC-stripe-webhook-S01-setup",
        label="Init",
        stage="write-tests",
    )
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.wait_for_function(
            f"""() => document.querySelector('{_TARGET} .resume-card__breadcrumb')
                ?.textContent.includes('write-tests')"""
        )
        breadcrumb = page.inner_text(f"{_TARGET} .resume-card__breadcrumb")
        command = page.inner_text(f"{_TARGET} .inverted-command__text")

    from sdlc.state.model import State
    from sdlc.state.suggested_next import compute_suggested_next

    expected_command = compute_suggested_next(State(phase=3, epics={"epic-1": {}}))
    assert breadcrumb == (
        "Phase 3 / EPIC-stripe-webhook / EPIC-stripe-webhook-S01-setup / write-tests"
    )
    assert command == expected_command


def test_resume_card_live_shows_loading_state_before_first_poll_resolves(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Masthead DEF-3 fold: a neutral loading state renders before the first
    /api/resume poll resolves -- never a blank card."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=100"
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        page.route("**/api/resume", lambda route: None)  # never fulfilled -> stays pending
        page.goto(url, wait_until="load")
        page.wait_for_selector(f"{_TARGET} .resume-card__breadcrumb")
        assert page.inner_text(f"{_TARGET} .resume-card__breadcrumb") == "Loading…"
    finally:
        page.close()


def test_resume_card_live_updates_within_one_poll_cycle_and_announces_change(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """AC2 + DEF-5: a state change on disk is reflected within one poll cycle,
    and the persistent live region announces the change (never on first mount)."""
    base_url, repo_root = dashboard_repo
    _write_state(repo_root, phase=1, epics={})
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=100"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.wait_for_function(
            f"""() => document.querySelector('{_TARGET} .inverted-command__text')
                ?.textContent === '/sdlc-start \\"<idea>\\"'"""
        )

        _write_state(repo_root, phase=1, epics={"epic-1": {}})

        page.wait_for_function(
            f"""() => document.querySelector('{_TARGET} .inverted-command__text')
                ?.textContent === 'sdlc scan'""",
            timeout=3_000,
        )
        live_text_after = page.inner_text(f"{_TARGET} .resume-card__live-region")
        assert "Updated —" in live_text_after
        assert "sdlc scan" in live_text_after


def test_copy_button_copies_post_poll_command_not_stale_value(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Task 5: clicking copy after a poll copies the NEW command, not the one
    captured by an earlier closure/render."""
    base_url, repo_root = dashboard_repo
    _write_state(repo_root, phase=1, epics={})
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=100"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.wait_for_function(
            f"""() => document.querySelector('{_TARGET} .inverted-command__text')
                ?.textContent === '/sdlc-start \\"<idea>\\"'"""
        )
        _write_state(repo_root, phase=1, epics={"epic-1": {}})
        page.wait_for_function(
            f"""() => document.querySelector('{_TARGET} .inverted-command__text')
                ?.textContent === 'sdlc scan'""",
            timeout=3_000,
        )
        page.evaluate(
            """() => {
              window.__copied = null;
              navigator.clipboard.writeText = async (text) => { window.__copied = text; };
            }"""
        )
        page.click(f"{_TARGET} .copy-btn")
        copied = page.evaluate("() => window.__copied")
        assert copied == "sdlc scan"


def test_resume_card_live_in_flight_guard_prevents_overlapping_polls(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Masthead DEF-1 fold: a poll slower than the interval must never overlap
    with the next tick."""
    base_url, _repo_root = dashboard_repo
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        page.add_init_script(
            """
            window.__concurrent = 0;
            window.__maxConcurrent = 0;
            const realFetch = window.fetch.bind(window);
            window.fetch = async (url, opts) => {
              if (!String(url).includes('/api/resume')) {
                return realFetch(url, opts);
              }
              window.__concurrent += 1;
              window.__maxConcurrent = Math.max(window.__maxConcurrent, window.__concurrent);
              await new Promise((r) => setTimeout(r, 150));
              try {
                return await realFetch(url, opts);
              } finally {
                window.__concurrent -= 1;
              }
            };
            """
        )
        url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=30"
        page.goto(url, wait_until="load")
        page.wait_for_timeout(700)
        assert page.evaluate("() => window.__maxConcurrent") == 1
    finally:
        page.close()


def test_resume_card_live_abort_controller_fires_on_disconnect(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Masthead DEF-1 fold (AbortController half): disconnecting the element
    mid-flight aborts the in-flight request's signal."""
    base_url, _repo_root = dashboard_repo
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        page.add_init_script(
            """
            window.__lastSignal = null;
            const realFetch = window.fetch.bind(window);
            window.fetch = async (url, opts) => {
              if (!String(url).includes('/api/resume')) {
                return realFetch(url, opts);
              }
              window.__lastSignal = opts && opts.signal;
              await new Promise((r) => setTimeout(r, 2_000));
              return realFetch(url, opts);
            };
            """
        )
        url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=100"
        page.goto(url, wait_until="load")
        page.wait_for_function("() => window.__lastSignal != null")
        page.evaluate(f"""() => document.querySelector('{_TARGET}').remove()""")
        aborted = page.evaluate("() => window.__lastSignal.aborted")
        assert aborted is True
    finally:
        page.close()


def test_resume_card_first_session_attribute_burst_shows_greeting_exactly_once(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """DEF-8: a custom-element upgrade with several observed attributes present
    at parse time fires attributeChangedCallback once per attribute, all before
    connectedCallback -- without coalescing, an earlier phantom render consumes
    the once-per-session greeting flag before the real render paints, and the
    greeting never appears. With coalescing, exactly one render happens and the
    first-session greeting shows."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.evaluate(
            """() => {
              sessionStorage.clear();
              const el = document.createElement('resume-card');
              el.id = 'resume-card-burst-target';
              el.setAttribute('user', 'diep');
              el.setAttribute('breadcrumb', '["Epic 5","Story 5.18"]');
              el.setAttribute('command', 'sdlc scan');
              document.body.appendChild(el);
            }"""
        )
        page.wait_for_selector("#resume-card-burst-target .resume-card__breadcrumb")
        greeting = page.inner_text("#resume-card-burst-target .resume-card__greeting")
        assert greeting == "Welcome, diep."
        greeting_count = page.eval_on_selector_all(
            "#resume-card-burst-target .resume-card__greeting", "els => els.length"
        )
        assert greeting_count == 1


def test_normalize_command_collapses_interior_newlines(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D5 (folds 5.8 DEF-1): an untrusted multi-line command collapses to a
    single space-joined line before it is ever copyable."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        result = page.evaluate(
            """async () => {
              const { normalizeCommand } = await import(
                '/static/components/resume-card/resume-card.js'
              );
              return normalizeCommand('sdlc scan\\n  --deep\\n');
            }"""
        )
    assert result == "sdlc scan --deep"


def test_hostile_cursor_breadcrumb_renders_as_inert_text(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Task 2 data-validation: a hostile breadcrumb part (e.g. injected markup)
    must render as literal, inert text -- never parsed as HTML. The real
    /api/resume route always sources cursor parts from validated canonical
    epic/story ids, so this exercises the CLIENT's textContent-only rendering
    defensively, independent of what the real server can produce today."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}"
    payload = '<img src=x onerror=alert(1)>"><script>alert(2)</script>'
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.evaluate(
            """(payload) => {
              const el = document.createElement('resume-card');
              el.id = 'resume-card-hostile-target';
              el.setAttribute('show-greeting', 'false');
              el.setAttribute('breadcrumb', JSON.stringify(['Phase 1', payload]));
              document.body.appendChild(el);
            }""",
            payload,
        )
        page.wait_for_selector("#resume-card-hostile-target .resume-card__breadcrumb")
        data = page.evaluate(
            """() => {
              const el = document.querySelector(
                '#resume-card-hostile-target .resume-card__breadcrumb'
              );
              return {
                text: el.textContent,
                childElementCount: el.childElementCount,
                hasInjectedImg: !!el.querySelector('img'),
                hasInjectedScript: !!el.querySelector('script'),
              };
            }"""
        )
    assert payload in data["text"]
    assert data["childElementCount"] == 0
    assert not data["hasInjectedImg"]
    assert not data["hasInjectedScript"]


def test_inverted_command_text_has_overflow_policy_applied(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """DEF-4: the computed style enforces single-line, scrollable overflow."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}"
    with _with_playwright_page(_browser, url, f"{_TARGET} .resume-card") as page:
        page.wait_for_selector(f"{_TARGET} .inverted-command__text")
        style = page.eval_on_selector(
            f"{_TARGET} .inverted-command__text",
            """el => ({
                overflowX: getComputedStyle(el).overflowX,
                whiteSpace: getComputedStyle(el).whiteSpace,
            })""",
        )
    assert style["overflowX"] == "auto"
    assert style["whiteSpace"] == "pre"

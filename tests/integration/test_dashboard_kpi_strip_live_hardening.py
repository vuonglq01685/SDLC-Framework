"""Playwright lifecycle/hardening contracts for the KPI Strip live poller (Story 5.17).

Sibling of ``test_dashboard_kpi_strip_live.py`` (split to stay under the
400-LOC/file cap). Covers Task 4/6 hardening: unchanged-signature no-teardown
(NFR-PERF-4), in-flight re-entrancy guard, AbortController-on-disconnect, and
inert rendering of hostile numerics. Shared payload builders + selectors are in
``_kpi_strip_live_support.py``.
"""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

from ._kpi_strip_live_support import (
    _LIVE_FIXTURE,
    _STRIP,
    _TARGET,
    _dora_payload,
    _mock_dora_route,
)

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration


@pytest.fixture()
def dashboard_repo(tmp_path: Path) -> Generator[tuple[str, Path], None, None]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/dora", timeout=1) as resp:
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


def test_kpi_strip_unchanged_poll_does_not_teardown_cells(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """NFR-PERF-4: unchanged signature keeps the same cell DOM nodes across polls."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=100"
    payload = _dora_payload()
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_selector(_STRIP)
        page.wait_for_function(
            f"""() => document.querySelectorAll('{_TARGET} .kpi-strip__hero').length === 4"""
        )
        # Tag the live hero node. `renderKpiStrip` rebuilds via `replaceChildren`,
        # so if an unchanged-signature poll re-rendered the strip the marked node
        # would be discarded and the marker lost. A DOM handle compared with `==`
        # is useless here (Playwright serializes elements to `{}`), so assert on a
        # marker that only survives if the node itself is preserved.
        page.eval_on_selector(
            f"{_TARGET} .kpi-strip__cell:nth-child(1) .kpi-strip__hero",
            "el => { el.dataset.teardownMarker = 'kept'; }",
        )
        page.wait_for_timeout(350)  # >= 3 poll cycles at intervalMs=100
        marker = page.eval_on_selector(
            f"{_TARGET} .kpi-strip__cell:nth-child(1) .kpi-strip__hero",
            "el => el.dataset.teardownMarker || null",
        )
        assert marker == "kept"
    finally:
        page.close()


def test_kpi_strip_live_in_flight_guard_prevents_overlapping_polls(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    base_url, _repo_root = dashboard_repo
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        page.add_init_script(
            """
            window.__concurrent = 0;
            window.__maxConcurrent = 0;
            const realFetch = window.fetch.bind(window);
            window.fetch = async (url, opts) => {
              if (!String(url).includes('/api/dora')) {
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


def test_kpi_strip_live_abort_controller_fires_on_disconnect(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    base_url, _repo_root = dashboard_repo
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        page.add_init_script(
            """
            window.__lastSignal = null;
            const realFetch = window.fetch.bind(window);
            window.fetch = async (url, opts) => {
              if (!String(url).includes('/api/dora')) {
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


def test_kpi_strip_hostile_numeric_renders_inert_no_data(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Task 1: a parseable-but-nonsensical numeric (negative hours) is coerced by
    the mapper to an inert no-data cell (``n/a`` real text, no injected markup).

    Uses a VALID-JSON hostile value on purpose: a bare ``NaN`` token is invalid
    JSON, so ``response.json()`` would throw and the strip would merely stay on
    its all-no-data loading placeholder -- never reaching
    ``isValidNonNegative``/``isValidRatio``. A negative ``value`` parses cleanly
    and drives the mapper's coercion path, which is the behaviour under test.
    """
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        lead_7d={
            "data_status": "ok",
            "value": -999.0,
            "unit": "hours",
        },
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_selector(_STRIP)
        # Require a MAPPED render (value heroes exist for the ok metrics) so the
        # assertion targets the mapper's coercion of the negative lead_time, not
        # the pre-poll loading placeholder (which is all no-data).
        page.wait_for_function(
            f"""() => document.querySelectorAll('{_TARGET} .kpi-strip__hero').length >= 1"""
        )
        cell = page.query_selector(f"{_TARGET} .kpi-strip__cell:nth-child(2)")  # type: ignore[attr-defined]
        data = page.evaluate(
            """(el) => {
              const valueEl = el.querySelector(
                '.kpi-strip__value, .kpi-strip__value--no-data'
              );
              return {
                valueText: valueEl ? valueEl.textContent : null,
                childElementCount: valueEl ? valueEl.childElementCount : 0,
                hasScript: !!el.querySelector('script'),
              };
            }""",
            cell,
        )
        assert data["valueText"] == "n/a"
        assert data["childElementCount"] == 0
        assert not data["hasScript"]
    finally:
        page.close()

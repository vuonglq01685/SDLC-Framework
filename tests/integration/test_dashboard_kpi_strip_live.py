"""Playwright behavioral contracts for the KPI Strip real-data path (Story 5.17).

Core AC witnesses: AC1 (5 cells from ``/api/dora``), AC2 (7d-vs-30d deltas with
per-metric sentiment), AC3 (insufficient_data -> n/a). Lifecycle/hardening
witnesses (in-flight guard, AbortController-on-disconnect, unchanged-signature
no-teardown, hostile numerics) live in the sibling
``test_dashboard_kpi_strip_live_hardening.py`` to keep each module under the
400-LOC/file cap. Shared payload builders + selectors are in
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
    _CELL1_DELTA_UP,
    _CELL2_DELTA_NEUTRAL,
    _CELL4_DELTA_DOWN,
    _CELL4_DELTA_UP,
    _CELLS,
    _LIVE_FIXTURE,
    _NO_DATA_VALUES,
    _STRIP,
    _TARGET,
    _dora_payload,
    _metric,
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


def test_kpi_strip_live_renders_five_cells_from_dora_payload(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """AC1: 4 DORA metrics + 1 documented placeholder populate the strip."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, _dora_payload())
        page.goto(url, wait_until="load")
        page.wait_for_selector(_STRIP)
        page.wait_for_function(
            f"""() => {{
              const heroes = document.querySelectorAll('{_TARGET} .kpi-strip__hero');
              return heroes.length === 4 && heroes[0].textContent === '2.4';
            }}"""
        )
        labels = page.eval_on_selector_all(
            f"{_TARGET} .kpi-strip__label", "els => els.map(e => e.textContent)"
        )
        assert labels[0] == "DEPLOY FREQUENCY"
        assert labels[1] == "LEAD TIME FOR CHANGES"
        assert labels[2] == "CHANGE FAIL RATE"
        assert labels[3] == "MTTR"
        assert labels[4] == "PROJECT KPI"
        assert page.inner_text(f"{_TARGET} .kpi-strip__value--no-data") == "n/a"
    finally:
        page.close()


def test_kpi_strip_live_insufficient_data_renders_na_with_reason(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """AC3: insufficient_data on the 7d window renders n/a real text + reason."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        cfr_7d=_metric(data_status="insufficient_data", unit="ratio"),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_selector(_STRIP)
        page.wait_for_function(
            f"""() => document.querySelectorAll('{_NO_DATA_VALUES}').length >= 1"""
        )
        cells = page.query_selector_all(_CELLS)  # type: ignore[attr-defined]
        cfr_cell = cells[2]
        assert cfr_cell.query_selector(".kpi-strip__value--no-data").inner_text() == "n/a"  # type: ignore[union-attr]
        reason_id = cfr_cell.query_selector(".kpi-strip__value--no-data").get_attribute(  # type: ignore[union-attr]
            "aria-describedby"
        )
        reason = page.inner_text(f"#{reason_id}")
        assert "insufficient" in reason.lower() or "data" in reason.lower()
    finally:
        page.close()


def test_kpi_strip_mttr_decrease_renders_green_delta_up(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D3: lower-is-better mttr decrease is an improvement -> delta--up (green)."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        mttr_7d=_metric(value=1.2, unit="hours", recovery_count=1),
        mttr_30d=_metric(value=2.0, unit="hours", recovery_count=2),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_function(f"""() => document.querySelector('{_CELL4_DELTA_UP}')""")
    finally:
        page.close()


def test_kpi_strip_deployment_frequency_increase_renders_green_delta_up(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D3: higher-is-better deployment_frequency increase -> delta--up (green)."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        deploy_7d=_metric(value=5, unit="deploys_per_window", per_day=0.6),
        deploy_30d=_metric(value=10, unit="deploys_per_window", per_day=0.4),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_function(f"""() => document.querySelector('{_CELL1_DELTA_UP}')""")
    finally:
        page.close()


def test_kpi_strip_mttr_regression_renders_red_delta_down(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D3: mttr increase is a regression -> delta--down (red)."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        mttr_7d=_metric(value=3.0, unit="hours", recovery_count=1),
        mttr_30d=_metric(value=2.0, unit="hours", recovery_count=2),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_function(f"""() => document.querySelector('{_CELL4_DELTA_DOWN}')""")
    finally:
        page.close()


def test_kpi_strip_lower_is_better_improvement_delta_has_no_double_sign(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """P1 regression: an improvement on a lower-is-better metric renders a clean
    ``↑ +<mag> vs 30d`` delta -- never the doubled ``+-`` sign produced when a
    raw-signed negative magnitude collides with the frozen ``+``-for-up prefix in
    ``formatDeltaLine``. Covers lead_time, change_failure_rate, and mttr."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        lead_7d=_metric(value=18.0, unit="hours"),
        lead_30d=_metric(value=21.0, unit="hours"),
        cfr_7d=_metric(value=0.20, unit="ratio", failed_count=1, total_count=5),
        cfr_30d=_metric(value=0.30, unit="ratio", failed_count=3, total_count=10),
        mttr_7d=_metric(value=1.2, unit="hours", recovery_count=1),
        mttr_30d=_metric(value=2.0, unit="hours", recovery_count=2),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_selector(_STRIP)
        # cell 2 = lead_time, 3 = change_failure_rate, 4 = mttr: all improved.
        for nth in (2, 3, 4):
            selector = f"{_TARGET} .kpi-strip__cell:nth-child({nth}) .kpi-strip__delta--up"
            page.wait_for_function(f"() => document.querySelector('{selector}')")
            text = page.inner_text(selector)
            assert "+-" not in text, f"doubled sign in delta: {text!r}"
            assert "-" not in text, f"raw negative leaked into delta: {text!r}"
            assert "vs 30d" in text
    finally:
        page.close()


def test_kpi_strip_no_30d_baseline_renders_neutral_delta(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D1: 7d ok but 30d insufficient -> neutral delta, no invented comparison."""
    base_url, _repo_root = dashboard_repo
    url = f"{base_url}{_LIVE_FIXTURE}?intervalMs=150"
    payload = _dora_payload(
        lead_30d=_metric(data_status="insufficient_data", unit="hours"),
    )
    page = _browser.new_page()  # type: ignore[attr-defined]
    try:
        _mock_dora_route(page, payload)
        page.goto(url, wait_until="load")
        page.wait_for_function(
            f"""() => {{
              const delta = document.querySelector('{_CELL2_DELTA_NEUTRAL}');
              return delta && delta.textContent.toLowerCase().includes('baseline');
            }}"""
        )
    finally:
        page.close()

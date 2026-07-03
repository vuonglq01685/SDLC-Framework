"""Playwright behavioral contracts for the Activity Feed real-data path (Story 5.16).

Split out of ``test_dashboard_activity_feed_empty_state.py`` (Story 5.11) to stay under
the 400-LOC/file cap (Architecture §765 + NFR-MAINT-3) once the real ``agent_runs.jsonl``
-backed tests were added. These execute the real ``/api/activity`` route + the live poller
in a browser DOM, proving AC1 (real fields, reverse-chronological) and AC2 (do-not-regress
the 5.11 newest-on-top / bounded-to-50 / incremental-render contract with real data), plus
the Task 6 untrusted-input / XSS-safety requirements.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_LIVE_FEED_FIXTURE = (
    "/static/components/activity-feed/activity-feed-live.fixture.html?intervalMs=150"
)
_FEED_ROWS = "#activity-feed-target .activity-feed__entry"


def _agent_run_record(
    *,
    run_id: str,
    ts: str,
    specialist_name: str = "dev-story",
    target_path: str = "5-16",
    workflow_step: str = "implementation",
    outcome: str = "success",
    duration_ms: int = 70_000,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "ts": ts,
        "specialist_name": specialist_name,
        "target_path": target_path,
        "target_kind": "primary",
        "workflow_step": workflow_step,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "attempts": 1,
        "tokens_in": 100,
        "tokens_out": 200,
        "mock": False,
    }


def _write_agent_runs(repo_root: Path, records: list[dict[str, object]]) -> Path:
    runs_dir = repo_root / "03-Implementation"
    runs_dir.mkdir(parents=True, exist_ok=True)
    runs_path = runs_dir / "agent_runs.jsonl"
    runs_path.write_text(
        "".join(json.dumps(r) + "\n" for r in records),
        encoding="utf-8",
    )
    return runs_path


def _append_agent_run(runs_path: Path, record: dict[str, object]) -> None:
    with runs_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


@pytest.fixture()
def dashboard_repo(tmp_path: Path) -> Generator[tuple[str, Path], None, None]:
    """Like the 5.11 ``dashboard_base_url`` fixture but also returns ``repo_root`` so a
    test can write/append real ``agent_runs.jsonl`` records mid-test (Story 5.16)."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/activity", timeout=1) as resp:
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
    """One Chromium instance for the whole module (Story 5.16 hardening) -- see the
    identical fixture in ``test_dashboard_activity_feed_empty_state.py`` for why."""
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
    browser: object, url: str, ready_selector: str, *, wait_until: str = "networkidle"
) -> Iterator[object]:
    page = browser.new_page()  # type: ignore[attr-defined]
    try:
        # The live-fixture page polls /api/activity every 150ms in these tests -- network
        # is never idle, so "networkidle" would hang until Playwright's own timeout.
        page.goto(url, wait_until=wait_until)
        page.wait_for_selector(ready_selector)
        yield page
    finally:
        page.close()


def test_activity_feed_live_renders_real_fields_reverse_chronological(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Story 5.16 AC1: real ts/agent/target/stage/outcome/duration, newest first."""
    base_url, repo_root = dashboard_repo
    _write_agent_runs(
        repo_root,
        [
            _agent_run_record(run_id="a", ts="2026-06-26T10:00:00.000Z"),
            _agent_run_record(run_id="b", ts="2026-06-26T12:00:00.000Z"),
            _agent_run_record(run_id="c", ts="2026-06-26T11:00:00.000Z"),
        ],
    )
    url = f"{base_url}{_LIVE_FEED_FIXTURE}"
    with _with_playwright_page(_browser, url, _FEED_ROWS, wait_until="load") as page:
        page.wait_for_function(f"document.querySelectorAll({_FEED_ROWS!r}).length === 3")
        data = page.evaluate(
            f"""() => [...document.querySelectorAll({_FEED_ROWS!r})].map((r) => ({{
                id: r.dataset.entryId,
                agent: r.querySelector('.activity-feed__agent').textContent,
                target: r.querySelector('.activity-feed__target').textContent,
                stage: r.querySelector('.activity-feed__stage').textContent,
                outcome: r.querySelector('.activity-feed__outcome-label').textContent,
                duration: r.querySelector('.activity-feed__duration').textContent,
            }}))"""
        )
        assert [row["id"] for row in data] == ["b", "c", "a"], "newest-on-top (AC1)"
        assert data[0]["agent"] == "dev-story"
        assert data[0]["target"] == "5-16"
        assert data[0]["stage"] == "implementation"
        assert data[0]["outcome"] == "Success"
        assert data[0]["duration"] == "1m 10s"


def test_activity_feed_live_poll_prepends_new_run_and_evicts_oldest(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Do-not-regress the 5.11 HIGH fix with REAL data: a poll prepends the
    newest run, stays bounded to 50, and the oldest genuinely evicts (AC2)."""
    base_url, repo_root = dashboard_repo
    records = [
        _agent_run_record(run_id=f"run-{i:03d}", ts=f"2026-06-26T10:{i:02d}:00.000Z")
        for i in range(50)
    ]
    runs_path = _write_agent_runs(repo_root, records)
    url = f"{base_url}{_LIVE_FEED_FIXTURE}"
    with _with_playwright_page(_browser, url, _FEED_ROWS, wait_until="load") as page:
        page.wait_for_function(f"document.querySelectorAll({_FEED_ROWS!r}).length === 50")
        page.evaluate(
            f"""() => document.querySelectorAll({_FEED_ROWS!r})
                .forEach((r) => {{ r.dataset.witness = 'keep'; }})"""
        )
        _append_agent_run(
            runs_path, _agent_run_record(run_id="run-new", ts="2026-06-26T11:00:00.000Z")
        )
        page.wait_for_function(
            f"""() => {{
                const rows = document.querySelectorAll({_FEED_ROWS!r});
                return rows.length > 0 && rows[0].dataset.entryId === 'run-new';
            }}"""
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
        assert after["topId"] == "run-new"
        assert "run-049" in after["ids"], "the newest historical run must NOT be evicted"
        assert "run-000" not in after["ids"], "the oldest run must scroll out (AC2)"
        assert after["freshlyCreated"] == ["run-new"], (
            "only the new row is created; existing nodes preserved (NFR-PERF-4)"
        )


def test_activity_feed_live_unknown_outcome_renders_neutral_not_error(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """D3/DEF-3: an outcome outside {success, failed} must NOT render the red
    error glyph — it gets a neutral treatment plus the raw outcome text."""
    base_url, repo_root = dashboard_repo
    _write_agent_runs(
        repo_root,
        [_agent_run_record(run_id="a", ts="2026-06-26T10:00:00.000Z", outcome="timeout")],
    )
    url = f"{base_url}{_LIVE_FEED_FIXTURE}"
    with _with_playwright_page(_browser, url, _FEED_ROWS, wait_until="load") as page:
        page.wait_for_function(f"document.querySelectorAll({_FEED_ROWS!r}).length === 1")
        data = page.evaluate(
            f"""() => {{
                const row = document.querySelector({_FEED_ROWS!r});
                const use = row.querySelector('.activity-feed__outcome-icon use');
                return {{
                    label: row.querySelector('.activity-feed__outcome-label').textContent,
                    href: use.getAttribute('href'),
                }};
            }}"""
        )
        assert data["label"] == "timeout", "raw outcome text must render verbatim"
        assert data["href"].endswith("#warning"), "unknown outcome must use the neutral glyph"
        assert not data["href"].endswith("#error"), "unknown outcome must NOT be red error"


def test_activity_feed_live_xss_payload_renders_as_inert_text(
    _browser: object, dashboard_repo: tuple[str, Path]
) -> None:
    """Task 6: untrusted agent_runs.jsonl content must never become markup."""
    base_url, repo_root = dashboard_repo
    payload = '<img src=x onerror=alert(1)>"><script>alert(2)</script>'
    _write_agent_runs(
        repo_root,
        [_agent_run_record(run_id="a", ts="2026-06-26T10:00:00.000Z", specialist_name=payload)],
    )
    url = f"{base_url}{_LIVE_FEED_FIXTURE}"
    with _with_playwright_page(_browser, url, _FEED_ROWS, wait_until="load") as page:
        page.wait_for_function(f"document.querySelectorAll({_FEED_ROWS!r}).length === 1")
        data = page.evaluate(
            f"""() => {{
                const row = document.querySelector({_FEED_ROWS!r});
                const agentCell = row.querySelector('.activity-feed__agent');
                return {{
                    text: agentCell.textContent,
                    childElementCount: agentCell.childElementCount,
                    hasInjectedImg: !!row.querySelector('img'),
                    hasInjectedScript: !!row.querySelector('script'),
                }};
            }}"""
        )
        assert data["text"] == payload, "payload must render verbatim as inert text"
        assert data["childElementCount"] == 0, "no markup created from the payload"
        assert not data["hasInjectedImg"]
        assert not data["hasInjectedScript"]

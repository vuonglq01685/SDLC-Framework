"""Shared Playwright helpers for dashboard a11y tests (Story 5.12)."""

from __future__ import annotations

import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread

pytest.importorskip("playwright")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AXE_VENDOR = _REPO_ROOT / "tests" / "dashboard" / "vendor" / "axe.min.js"
_COMPOSITE_FIXTURE = "/static/test-fixtures/editorial-scanning-rhythm.html"

# D2: Level A tags only — there is NO wcag22a tag in axe-core.
AXE_BLOCK_TAGS = frozenset({"wcag2a", "wcag21a"})
AXE_RUN_TAGS = [
    "wcag2a",
    "wcag21a",
    "wcag2aa",
    "wcag21aa",
    "wcag22aa",
]
AXE_OPTIONS = {
    "runOnly": {"type": "tag", "values": AXE_RUN_TAGS},
    "resultTypes": ["violations"],
}


@pytest.fixture()
def dashboard_composite_url(tmp_path: Path) -> Generator[str, None, None]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{base_url}{_COMPOSITE_FIXTURE}",
                timeout=1,
            ) as resp:
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    yield f"{base_url}{_COMPOSITE_FIXTURE}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@contextmanager
def with_playwright_page(url: str) -> Iterator[object]:
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


def run_axe_scan(page: object) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run axe and partition violations into blocking (Level A) vs reported (AA)."""
    page.add_script_tag(path=str(_AXE_VENDOR))
    raw = page.evaluate("(opts) => axe.run(document, opts)", AXE_OPTIONS)
    violations = raw.get("violations", [])
    blocking: list[dict[str, object]] = []
    reported: list[dict[str, object]] = []
    for violation in violations:
        tags = set(violation.get("tags", []))
        if tags & AXE_BLOCK_TAGS:
            blocking.append(violation)
        else:
            reported.append(violation)
    return blocking, reported


def format_axe_violation(violation: dict[str, object]) -> str:
    rule_id = violation.get("id", "?")
    help_url = violation.get("helpUrl", "")
    nodes = violation.get("nodes", [])
    targets = [node.get("target") for node in nodes if isinstance(node, dict)]
    return f"{rule_id} targets={targets} helpUrl={help_url}"


def assert_live_dots_have_text_labels(page: object) -> None:
    """AC4 / D4: every rendered <live-dot> must have a non-empty text label."""
    result = page.evaluate(
        """() => {
          const dots = Array.from(document.querySelectorAll('live-dot'));
          const missing = [];
          for (const dot of dots) {
            const label = dot.querySelector('.live-dot__label');
            const text = label ? label.textContent.trim() : '';
            if (!text) {
              missing.push(dot.outerHTML.slice(0, 120));
            }
          }
          return missing;
        }""",
    )
    assert result == [], f"live-dot without adjacent text label: {result}"

"""Shared Playwright helpers for dashboard a11y tests (Story 5.12).

The ``dashboard_composite_url`` fixture lives in ``tests/dashboard/conftest.py``
(not here) so pytest can resolve it for the integration modules that import only
these functions — a fixture defined in an imported non-conftest module is invisible
to pytest. See Story 5.12 review (2026-07-01) P1.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

# Story 5.22 review P4: do NOT `pytest.importorskip("playwright")` at module
# scope. The pure helpers below (format_axe_violation, the tag constants,
# RELEASE_SURFACE_FIXTURE_PATH, wait_for_release_surface_render,
# assert_release_surface_complete) need no browser, so a module-level skip
# needlessly couples browserless unit tests (which import this module transitively
# via scripts/generate_a11y_report.py) to the Playwright package. The browser
# dependency is guarded lazily inside with_playwright_page instead — every
# browser-using test routes through it, so the skip semantics are preserved.

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AXE_VENDOR = _REPO_ROOT / "tests" / "dashboard" / "vendor" / "axe.min.js"

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


@contextmanager
def with_playwright_page(url: str) -> Iterator[object]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - env without the playwright pkg
        pytest.skip(f"playwright package not installed: {exc}")

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


# Story 5.22 D1: the terminal release-gate fixture, shared between the pytest
# module (test_release_a11y_surface.py) and scripts/generate_a11y_report.py so
# the "what surface did we actually scan" wait-logic can't drift between them.
RELEASE_SURFACE_FIXTURE_PATH = "/static/test-fixtures/release-a11y-surface.html"


def wait_for_release_surface_render(page: object) -> None:
    """Block until every 5C surface in the release-a11y-surface fixture has mounted."""
    page.wait_for_selector("dashboard-tabs [role='tab']")
    page.wait_for_selector("kpi-strip dl")  # review P2/A3: gate the KPI rhythm surface too
    page.wait_for_selector("backlog-tree .tree-expander")
    page.wait_for_selector("resume-card .copy-btn")
    page.wait_for_selector(".stop-banner")
    page.wait_for_selector(".honest-disconnection-banner")
    page.wait_for_selector(".viewport-banner")


def assert_release_surface_complete(page: object) -> None:
    """Guard that the release fixture actually rendered every 5C gap surface.

    ``wait_for_release_surface_render`` only proves *presence* of ``.stop-banner``,
    which the honest-disconnection banner alone satisfies (it reuses the
    ``stop-banner alert crit`` treatment), so a page whose 7 real STOP triggers
    silently failed to render would still scan and *vacuously* pass. This asserts
    the full 5C gap surface so both the terminal test AND the release-report
    script (``scripts/generate_a11y_report.py``) enforce ONE completeness
    contract rather than the script gating on mere presence (Story 5.22 review P2).
    """
    stop_banners = page.locator("#alertsHost .stop-banner")
    stop_count = stop_banners.count()
    assert stop_count == 7, f"expected 7 STOP triggers in #alertsHost, found {stop_count}"
    labels = page.locator("#alertsHost .stop-banner__title").all_inner_texts()
    for severity in ("CRITICAL:", "WARNING:", "INFO:"):
        assert any(severity in text for text in labels), f"missing STOP severity {severity}"
    disconnection = page.locator(".honest-disconnection-banner")
    assert disconnection.count() == 1, "missing the honest-disconnection banner"
    assert disconnection.get_attribute("role") == "alert", "disconnection banner role != alert"
    disconnected_copy = page.locator("resume-card#resume-card-disconnected .copy-btn")
    assert disconnected_copy.get_attribute("aria-disabled") == "true", (
        "disconnected resume-card copy button is not aria-disabled"
    )
    viewport = page.locator(".viewport-banner")
    assert viewport.count() == 1, "missing the viewport degradation banner"
    assert viewport.get_attribute("role") == "status", "viewport banner role != status"


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

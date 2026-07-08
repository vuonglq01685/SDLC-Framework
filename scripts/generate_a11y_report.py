"""Thin a11y release-report generator (Story 5.22 Task 2 / D2).

Runs the full-surface terminal axe scan (``release-a11y-surface.html``, the
same fixture/harness Story 5.22 D1 introduced) plus the existing Story 5.12
keyboard-only smoke suite, and emits a deterministic Markdown report section
suitable for pasting into ``docs/a11y/release-<version>.md`` (D3).

This is deliberately thin: it reuses ``tests/dashboard/_playwright_a11y.py``
(``run_axe_scan``, ``format_axe_violation``, ``with_playwright_page``,
``wait_for_release_surface_render``, ``assert_release_surface_complete``)
rather than reinventing the scan, and reuses the existing
``sdlc.dashboard.server`` HTTP harness to serve the fixture deterministically
(no live ``sdlc dashboard``, no real backend).

Exit codes (distinct so a caller can tell a real a11y regression from an
infra failure — Story 5.22 review P3):
  0  PASS — zero Level-A (blocking) axe violations AND the keyboard-only
     smoke suite actually ran and passed.
  1  FAIL — at least one Level-A violation, a keyboard-suite failure, or a
     required release surface failed to render. A real a11y regression: this
     is the AC3 "release is blocked" hook, so any CI/pre-commit invocation of
     this script fails closed on a regression.
  2  ENVIRONMENT — the scan could not run (Playwright/Chromium missing, or the
     test HTTP server never came up). NOT an a11y verdict; a report body is
     still emitted with ``A11Y-REPORT-STATUS: FAIL`` and an Environment section
     so a CI grep for the status line still finds it.

Usage: ``uv run python scripts/generate_a11y_report.py [--date YYYY-MM-DD] [--out PATH]``
``--date`` overrides the embedded report date (determinism for tests / reproducible
diffs); defaults to today (UTC). ``--out`` writes ONLY the report body to a file
(byte-clean, safe to paste verbatim into ``docs/a11y/release-<version>.md``) and is
the recommended form — the nested keyboard-suite run prints its own pytest
progress/summary to stdout, which would otherwise interleave into a
stdout-redirected report body.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

import pytest

# Story 5.22 D2 (Dev Notes): mirror the sys.path shim tests/conftest.py already
# uses (inserting the repo's `tests/` root) so `tests/dashboard/` resolves as
# the `dashboard` namespace package (PEP 420, no __init__.py — same mechanism
# pytest's own --import-mode=prepend relies on) and this script can reuse
# tests/dashboard/_playwright_a11y.py verbatim without duplicating the
# axe-scan plumbing. Kept out of src/sdlc/ entirely (tooling, like
# freeze_wireformat_snapshots.py); this is also why `mypy_path = ["src",
# "tests"]` in pyproject.toml resolves this import for `mypy --strict`.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_TESTS_DIR = str(_REPO_ROOT / "tests")
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from dashboard._playwright_a11y import (  # noqa: E402
    RELEASE_SURFACE_FIXTURE_PATH,
    assert_release_surface_complete,
    format_axe_violation,
    run_axe_scan,
    wait_for_release_surface_render,
    with_playwright_page,
)
from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread  # noqa: E402

_KEYBOARD_SUITE_PATH: Final[str] = "tests/dashboard/test_keyboard_only.py"
_HTTP_OK: Final[int] = 200
_SERVER_BOOT_TIMEOUT_S: Final[float] = 15.0  # review P8: was 5s — too tight for cold Chromium/CI

# The 7 named UX §8.5 smoke surfaces plus the 2 net-new 5C surfaces this
# story's terminal fixture adds (D1) — kept as a literal list (not derived
# from the fixture) so the report is a stable, human-reviewable checklist.
_SCANNED_SURFACES: Final[tuple[str, ...]] = (
    "masthead",
    "KPI strip",
    "resume card",
    "phase tracker",
    "backlog tree",
    "STOP banner (all 7 trigger types)",
    "activity feed",
    "disconnected state (honest-disconnection banner + resume card)",
    "viewport degradation banner",
)


class _ScanEnvironmentError(RuntimeError):
    """The scan could not run (no browser / server never came up) — infra, exit 2."""


class _SurfaceIncompleteError(RuntimeError):
    """A required release surface failed to render — a real regression, exit 1."""


def _today_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def report_passed(
    *,
    blocking: list[dict[str, object]],
    keyboard_passed: bool,
    environment_error: str | None = None,
) -> bool:
    """Single source of truth for the PASS/FAIL verdict.

    Used by BOTH ``build_report`` (the report status line) and ``main`` (the
    process exit code) so the two can never drift into a split-brain where the
    report says PASS while the process exits non-zero (Story 5.22 review P6).
    """
    return environment_error is None and not blocking and keyboard_passed


def _render_violation_section(title: str, violations: list[dict[str, object]]) -> str:
    ordered = sorted(violations, key=lambda v: (str(v.get("id", "")), format_axe_violation(v)))
    lines = [f"## {title}", "", f"Violations: {len(ordered)}", ""]
    if not ordered:
        lines.append("No violations.")
    else:
        lines.extend(f"- {format_axe_violation(v)}" for v in ordered)
    return "\n".join(lines)


def build_report(
    *,
    date: str,
    blocking: list[dict[str, object]],
    reported: list[dict[str, object]],
    keyboard_passed: bool,
    environment_error: str | None = None,
) -> str:
    """Pure function: render the deterministic Markdown report body.

    No I/O, no wall-clock reads — every input is explicit so the same
    arguments always produce byte-identical output (Dev Notes determinism
    guard). ``environment_error`` (review P3) forces FAIL and appends an
    Environment section so an infra failure is self-explanatory in the report.
    """
    status = (
        "PASS"
        if report_passed(
            blocking=blocking, keyboard_passed=keyboard_passed, environment_error=environment_error
        )
        else "FAIL"
    )
    if environment_error is not None:
        keyboard_status = "NOT RUN (scan environment unavailable)"
    else:
        keyboard_status = "PASS" if keyboard_passed else "FAIL"
    sections = [
        f"# Dashboard Accessibility Report — {date}",
        "",
        f"A11Y-REPORT-STATUS: {status}",
        "",
        _render_violation_section("Level A (WCAG 2.2, blocking)", blocking),
        "",
        _render_violation_section("Level AA (reported, non-blocking)", reported),
        "",
        "## Keyboard-only smoke test",
        "",
        f"Status: {keyboard_status}",
        f"Suite: {_KEYBOARD_SUITE_PATH} (Story 5.12)",
        "",
        "## Scanned surfaces",
        "",
        *(f"- {surface}" for surface in _SCANNED_SURFACES),
        "",
    ]
    if environment_error is not None:
        sections.extend(
            [
                "## Environment",
                "",
                f"Scan did not run: {environment_error}",
                "",
            ]
        )
    return "\n".join(sections)


def _chromium_unavailable_reason() -> str | None:
    """Return a human reason if a Chromium page cannot be driven, else None.

    Preflight so the script fails *closed* with an explicit, self-describing
    report (exit 2) instead of leaking a pytest-internal ``Skipped`` traceback
    and writing no report body when the browser is absent (Story 5.22 review P3).
    """
    try:
        from playwright.sync_api import Error as PlaywrightError  # noqa: PLC0415
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - env without the playwright pkg
        return f"playwright package not installed: {exc}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except PlaywrightError as exc:  # pragma: no cover - env without the browser binary
        return f"Chromium not installed (run `playwright install chromium`): {exc}"
    return None


def _run_axe_scan_over_release_surface() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Boot the deterministic test HTTP server + Playwright, scan, tear down.

    Mirrors ``running_dashboard``/``dashboard_composite_url`` in
    ``tests/dashboard/conftest.py`` (a script cannot depend on pytest
    fixtures directly, so the boot sequence is inlined here — kept minimal,
    same shape as the conftest fixtures it mirrors).

    Raises ``_ScanEnvironmentError`` when the browser/server are unavailable
    (exit 2) and ``_SurfaceIncompleteError`` when the fixture fails to render a
    required 5C surface (exit 1) — so ``main`` can distinguish an infra failure
    from a real a11y regression (Story 5.22 review P3/P2).
    """
    reason = _chromium_unavailable_reason()
    if reason is not None:
        raise _ScanEnvironmentError(reason)
    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        state_dir = repo_root / ".claude" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text('{"phase":1}', encoding="utf-8")
        port = find_free_port()
        server, thread = serve_dashboard_in_thread(repo_root=repo_root, port=port)
        base_url = f"http://127.0.0.1:{port}"
        url = f"{base_url}{RELEASE_SURFACE_FIXTURE_PATH}"
        deadline = time.monotonic() + _SERVER_BOOT_TIMEOUT_S
        try:
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=1) as resp:
                        if resp.status == _HTTP_OK:
                            break
                except urllib.error.HTTPError:
                    # The server responded (e.g. a 404 from a wrong fixture path):
                    # it IS up. Break and let the scan surface the real problem
                    # rather than mislabelling this as "server did not become
                    # ready" (review P8).
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise _ScanEnvironmentError(
                    f"dashboard server did not become ready within {_SERVER_BOOT_TIMEOUT_S:.0f}s"
                )
            with with_playwright_page(url) as page:
                wait_for_release_surface_render(page)
                try:
                    assert_release_surface_complete(page)
                except AssertionError as exc:
                    raise _SurfaceIncompleteError(str(exc)) from exc
                return run_axe_scan(page)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def keyboard_suite_green(*, exit_code: int, passed: int, failed: int) -> bool:
    """Green iff pytest succeeded AND at least one test actually ran to a pass.

    ``pytest.main`` returns 0 not only when tests pass but also when every
    collected test *skips* (e.g. no Chromium → ``with_playwright_page`` calls
    ``pytest.skip``). Reporting an all-skipped suite as a keyboard PASS is a
    false green, so we additionally require ``passed > 0`` and ``failed == 0``
    (Story 5.22 review P1).
    """
    return exit_code == 0 and passed > 0 and failed == 0


class _ResultCollector:
    """pytest plugin: tally passed/failed outcomes from an in-process run."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" and report.passed:
            self.passed += 1
        elif report.failed:
            self.failed += 1


def _run_keyboard_only_suite() -> bool:
    """Run the existing Story 5.12 keyboard-only smoke suite in-process.

    Reuses the suite verbatim (no re-implementation, per anti-scope) via
    pytest's public API rather than a subprocess — this script already runs
    as a standalone top-level process, so nesting pytest here does not
    collide with an outer pytest session. ``--no-cov`` disables the
    project-wide 87% coverage gate (``pyproject.toml`` addopts): running one
    suite in isolation would otherwise always report near-zero whole-repo
    coverage and fail this script for a reason unrelated to a11y.
    """
    collector = _ResultCollector()
    exit_code = pytest.main(
        ["-q", "--no-header", "--no-cov", "-p", "no:cacheprovider", _KEYBOARD_SUITE_PATH],
        plugins=[collector],
    )
    return keyboard_suite_green(
        exit_code=int(exit_code), passed=collector.passed, failed=collector.failed
    )


def _emit(report: str, out: Path | None) -> None:
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)  # review P8: don't crash on missing dir
        out.write_text(report, encoding="utf-8")
    else:
        print(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD) to embed in the report; defaults to today (UTC).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the report to this path instead of stdout.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    date = args.date or _today_iso()
    blocking: list[dict[str, object]] = []
    reported: list[dict[str, object]] = []
    keyboard_passed = False
    environment_error: str | None = None

    try:
        blocking, reported = _run_axe_scan_over_release_surface()
    except _ScanEnvironmentError as exc:
        environment_error = str(exc)
    except _SurfaceIncompleteError as exc:
        # A required 5C surface didn't render — surface it as a blocking
        # pseudo-violation so the report is self-explanatory and status = FAIL.
        blocking = [
            {"id": "release-surface-incomplete", "helpUrl": "", "nodes": [{"target": [str(exc)]}]}
        ]
    else:
        keyboard_passed = _run_keyboard_only_suite()

    report = build_report(
        date=date,
        blocking=blocking,
        reported=reported,
        keyboard_passed=keyboard_passed,
        environment_error=environment_error,
    )
    _emit(report, args.out)

    if environment_error is not None:
        return 2
    return 0 if report_passed(blocking=blocking, keyboard_passed=keyboard_passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())

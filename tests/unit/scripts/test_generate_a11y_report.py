"""Unit tests for scripts/generate_a11y_report.py (Story 5.22 Task 2 / D2).

Pure-function tests exercise ``build_report`` directly with synthetic axe
violation dicts (no Playwright/browser needed — this is a ``tests/unit/``
module per Dev Notes). ``main()`` orchestration tests monkeypatch the
scan/keyboard collaborators so the exit-code contract (AC3's blocking hook) is
verified without booting a real dashboard server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import generate_a11y_report as report_script

pytestmark = pytest.mark.unit

_LEVEL_A_VIOLATION = {
    "id": "image-alt",
    "helpUrl": "https://dequeuniversity.com/rules/axe/4.12/image-alt",
    "tags": ["wcag2a", "wcag111"],
    "nodes": [{"target": ["img#axe-red-witness"]}],
}
_LEVEL_AA_VIOLATION = {
    "id": "color-contrast",
    "helpUrl": "https://dequeuniversity.com/rules/axe/4.12/color-contrast",
    "tags": ["wcag2aa"],
    "nodes": [{"target": [".kpi-strip__value--no-data"]}],
}


def test_build_report_pass_when_clean() -> None:
    report = report_script.build_report(
        date="2026-07-08", blocking=[], reported=[], keyboard_passed=True
    )
    assert "A11Y-REPORT-STATUS: PASS" in report
    assert "2026-07-08" in report
    assert "Level A" in report
    assert "Violations: 0" in report


def test_build_report_fails_when_level_a_violation_present() -> None:
    report = report_script.build_report(
        date="2026-07-08",
        blocking=[_LEVEL_A_VIOLATION],
        reported=[],
        keyboard_passed=True,
    )
    assert "A11Y-REPORT-STATUS: FAIL" in report
    assert "image-alt" in report
    assert "img#axe-red-witness" in report


def test_build_report_fails_when_keyboard_test_fails() -> None:
    report = report_script.build_report(
        date="2026-07-08", blocking=[], reported=[], keyboard_passed=False
    )
    assert "A11Y-REPORT-STATUS: FAIL" in report
    assert "Keyboard-only smoke test" in report
    assert "Status: FAIL" in report


def test_build_report_lists_aa_reported_as_non_blocking() -> None:
    report = report_script.build_report(
        date="2026-07-08",
        blocking=[],
        reported=[_LEVEL_AA_VIOLATION],
        keyboard_passed=True,
    )
    assert "A11Y-REPORT-STATUS: PASS" in report
    assert "color-contrast" in report
    assert "Level AA" in report


def test_build_report_sorts_violations_deterministically() -> None:
    unordered = [_LEVEL_A_VIOLATION, dict(_LEVEL_A_VIOLATION, id="aaa-first-rule")]
    report_1 = report_script.build_report(
        date="2026-07-08", blocking=unordered, reported=[], keyboard_passed=True
    )
    reversed_order = list(reversed(unordered))
    report_2 = report_script.build_report(
        date="2026-07-08", blocking=reversed_order, reported=[], keyboard_passed=True
    )
    assert report_1 == report_2
    assert report_1.index("aaa-first-rule") < report_1.index("image-alt")


def test_build_report_lists_scanned_surfaces() -> None:
    report = report_script.build_report(
        date="2026-07-08", blocking=[], reported=[], keyboard_passed=True
    )
    for surface in (
        "masthead",
        "KPI",
        "resume card",
        "phase tracker",
        "backlog tree",
        "STOP banner",
        "activity feed",
        "disconnected",
        "viewport",
    ):
        assert surface.lower() in report.lower(), f"missing scanned surface: {surface}"


def test_build_report_is_repeatable_for_same_inputs() -> None:
    """No embedded wall-clock timestamps — determinism guard (Dev Notes D2)."""
    first = report_script.build_report(
        date="2026-07-08", blocking=[], reported=[], keyboard_passed=True
    )
    second = report_script.build_report(
        date="2026-07-08", blocking=[], reported=[], keyboard_passed=True
    )
    assert first == second


def test_main_exits_zero_and_prints_report_when_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: ([], []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: True)
    exit_code = report_script.main(["--date", "2026-07-08"])
    assert exit_code == 0
    assert "A11Y-REPORT-STATUS: PASS" in capsys.readouterr().out


def test_main_exits_nonzero_on_level_a_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        report_script,
        "_run_axe_scan_over_release_surface",
        lambda: ([_LEVEL_A_VIOLATION], []),
    )
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: True)
    assert report_script.main(["--date", "2026-07-08"]) == 1


def test_main_exits_nonzero_when_keyboard_suite_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: ([], []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: False)
    assert report_script.main(["--date", "2026-07-08"]) == 1


def test_main_writes_report_to_out_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: ([], []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: True)
    out_path = tmp_path / "release-a11y-report.md"
    exit_code = report_script.main(["--date", "2026-07-08", "--out", str(out_path)])
    assert exit_code == 0
    assert "A11Y-REPORT-STATUS: PASS" in out_path.read_text(encoding="utf-8")


def test_main_defaults_date_to_today_when_omitted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: ([], []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: True)
    monkeypatch.setattr(report_script, "_today_iso", lambda: "2030-01-01")
    assert report_script.main([]) == 0
    assert "2030-01-01" in capsys.readouterr().out


# --- review P1: keyboard suite must actually RUN to a pass, not merely exit 0 ---


@pytest.mark.parametrize(
    ("exit_code", "passed", "failed", "expected"),
    [
        (0, 3, 0, True),  # real passes
        (0, 0, 0, False),  # all-skipped (no Chromium) — pytest still exits 0
        (1, 2, 1, False),  # a genuine failure
        (5, 0, 0, False),  # no tests collected
    ],
)
def test_keyboard_suite_green_requires_a_real_pass(
    exit_code: int, passed: int, failed: int, expected: bool
) -> None:
    assert (
        report_script.keyboard_suite_green(exit_code=exit_code, passed=passed, failed=failed)
        is expected
    )


class _FakeReport:
    def __init__(self, when: str, *, passed: bool = False, failed: bool = False) -> None:
        self.when = when
        self.passed = passed
        self.failed = failed


def test_result_collector_ignores_skipped_setup_reports() -> None:
    collector = report_script._ResultCollector()
    collector.pytest_runtest_logreport(_FakeReport("setup"))  # a skip: neither passed nor failed
    collector.pytest_runtest_logreport(_FakeReport("call", passed=True))
    collector.pytest_runtest_logreport(_FakeReport("call", failed=True))
    assert collector.passed == 1
    assert collector.failed == 1


# --- review P6: build_report status and main exit code share one derivation ---


@pytest.mark.parametrize(
    ("blocking", "keyboard_passed"),
    [([], True), ([_LEVEL_A_VIOLATION], True), ([], False), ([_LEVEL_A_VIOLATION], False)],
)
def test_report_status_and_exit_code_never_disagree(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    blocking: list[dict[str, object]],
    keyboard_passed: bool,
) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: (blocking, []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: keyboard_passed)
    exit_code = report_script.main(["--date", "2026-07-08"])
    report = capsys.readouterr().out
    status_pass = "A11Y-REPORT-STATUS: PASS" in report
    assert status_pass == (exit_code == 0)


# --- review P3: infra failure (no browser / server) fails closed with exit 2 + a report ---


def test_build_report_environment_error_is_fail_with_section() -> None:
    report = report_script.build_report(
        date="2026-07-08",
        blocking=[],
        reported=[],
        keyboard_passed=True,
        environment_error="Chromium not installed",
    )
    assert "A11Y-REPORT-STATUS: FAIL" in report
    assert "## Environment" in report
    assert "Chromium not installed" in report


def test_main_environment_error_exits_two_and_still_emits_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        raise report_script._ScanEnvironmentError("no browser")

    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", _raise)
    exit_code = report_script.main(["--date", "2026-07-08"])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "A11Y-REPORT-STATUS: FAIL" in out
    assert "no browser" in out


def test_main_surface_incomplete_exits_one_and_reports_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        raise report_script._SurfaceIncompleteError("expected 7 STOP triggers, found 0")

    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", _raise)
    exit_code = report_script.main(["--date", "2026-07-08"])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "A11Y-REPORT-STATUS: FAIL" in out
    assert "expected 7 STOP triggers, found 0" in out


# --- review P8: --out to a not-yet-existing parent dir must not crash ---


def test_main_out_creates_missing_parent_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(report_script, "_run_axe_scan_over_release_surface", lambda: ([], []))
    monkeypatch.setattr(report_script, "_run_keyboard_only_suite", lambda: True)
    out_path = tmp_path / "does" / "not" / "exist" / "release-a11y.md"
    assert report_script.main(["--date", "2026-07-08", "--out", str(out_path)]) == 0
    assert "A11Y-REPORT-STATUS: PASS" in out_path.read_text(encoding="utf-8")

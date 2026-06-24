"""Unit tests for scripts/check_dashboard_color_only.py (Story 5.5 AC2 / §7.4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_color_only as color_only_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_color_only"


def test_scan_flags_bare_live_dot_without_label() -> None:
    path = _FIXTURES / "violation_bare_live_dot.html"
    violations = color_only_script.scan_paths([path])
    assert violations
    assert violations[0].line == 4


def test_scan_passes_live_dot_with_adjacent_label() -> None:
    path = _FIXTURES / "clean_live_dot_with_label.html"
    assert color_only_script.scan_paths([path]) == []


def test_main_returns_1_on_bare_live_dot(capsys: pytest.CaptureFixture[str]) -> None:
    path = _FIXTURES / "violation_bare_live_dot.html"
    assert color_only_script.main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "violation_bare_live_dot.html:4:" in err


def test_main_returns_0_on_paired_live_dot() -> None:
    path = _FIXTURES / "clean_live_dot_with_label.html"
    assert color_only_script.main([str(path)]) == 0


def test_scan_flags_multiline_bare_live_dot() -> None:
    # PATCH-3 regression: an opening tag split across lines must NOT escape the gate.
    path = _FIXTURES / "violation_multiline_bare.html"
    violations = color_only_script.scan_paths([path])
    assert violations
    assert violations[0].line == 4


def test_scan_flags_bare_live_dot_with_gt_in_attribute() -> None:
    # PATCH-3 regression: a '>' inside an attribute value must NOT split the tag early.
    path = _FIXTURES / "violation_attr_gt_bare.html"
    assert color_only_script.scan_paths([path])


def test_scan_passes_label_on_next_line() -> None:
    # PATCH-3 regression: a valid label on the next line is NOT a false positive.
    path = _FIXTURES / "clean_label_next_line.html"
    assert color_only_script.scan_paths([path]) == []


def test_scan_flags_empty_element_sibling_without_text() -> None:
    # PATCH-3 no-regression: an empty <div></div> sibling is not a text label.
    path = _FIXTURES / "violation_empty_element_sibling.html"
    assert color_only_script.scan_paths([path])


def test_scan_passes_text_tag_sibling_without_class() -> None:
    # PATCH-3: a sibling text tag carrying real text counts as the adjacent label.
    path = _FIXTURES / "clean_text_tag_sibling.html"
    assert color_only_script.scan_paths([path]) == []


def test_main_returns_2_on_missing_explicit_path() -> None:
    assert color_only_script.main(["/nonexistent/path.html"]) == 2


def test_cli_module_invocation() -> None:
    path = _FIXTURES / "violation_bare_live_dot.html"
    script = _REPO_ROOT / "scripts" / "check_dashboard_color_only.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "violation_bare_live_dot.html" in proc.stderr

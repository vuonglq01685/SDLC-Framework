"""Tests for scripts/check_dashboard_forbidden_patterns.py (Story 5.12 AC1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_forbidden_patterns as forbidden_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_forbidden_patterns"
_STATIC_ROOT = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"


def test_scan_flags_dialog_element() -> None:
    path = _FIXTURES / "violation_dialog.html"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert violations[0].pattern == "<dialog>"


def test_scan_flags_in_app_form() -> None:
    path = _FIXTURES / "violation_form.html"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert violations[0].pattern == "<form> (in-app)"


def test_scan_flags_data_toast_attribute() -> None:
    path = _FIXTURES / "violation_data_toast.html"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert "data-toast" in violations[0].pattern


def test_scan_flags_history_push_state() -> None:
    path = _FIXTURES / "violation_push_state.js"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert "pushState" in violations[0].pattern


def test_scan_flags_skeleton_loader_css_class() -> None:
    path = _FIXTURES / "violation_skeleton.css"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert "skeleton-loader" in violations[0].pattern


def test_scan_flags_modal_element() -> None:
    path = _FIXTURES / "violation_modal.html"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert violations[0].pattern == "<modal>"


def test_scan_flags_history_replace_state() -> None:
    path = _FIXTURES / "violation_replace_state.js"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert "replaceState" in violations[0].pattern


def test_scan_flags_skeleton_loader_html_class() -> None:
    path = _FIXTURES / "violation_skeleton_html_class.html"
    violations = forbidden_script.scan_paths([path])
    assert violations
    assert "skeleton-loader" in violations[0].pattern


def test_scan_flags_data_toast_boolean_attribute(tmp_path: Path) -> None:
    target = tmp_path / "boolean_toast.html"
    target.write_text("<div data-toast>hi</div>\n", encoding="utf-8")
    violations = forbidden_script.scan_paths([target])
    assert violations
    assert "data-toast" in violations[0].pattern


def test_scan_ignores_hyphenated_custom_elements(tmp_path: Path) -> None:
    target = tmp_path / "custom_elements.html"
    target.write_text("<dialog-box></dialog-box>\n<form-row></form-row>\n", encoding="utf-8")
    assert forbidden_script.scan_paths([target]) == []


def test_scan_ignores_pushstate_in_full_line_comment(tmp_path: Path) -> None:
    target = tmp_path / "doc_comment.js"
    target.write_text("// never call history.pushState() here\nconst x = 1;\n", encoding="utf-8")
    assert forbidden_script.scan_paths([target]) == []


def test_scan_flags_skeleton_bem_class_in_css(tmp_path: Path) -> None:
    target = tmp_path / "bem_skeleton.css"
    target.write_text(".loading-skeleton__row { opacity: 0.5; }\n", encoding="utf-8")
    violations = forbidden_script.scan_paths([target])
    assert violations
    assert "skeleton-loader" in violations[0].pattern


def test_scan_passes_role_tablist_without_false_positive() -> None:
    path = _FIXTURES / "clean_tabs_only.html"
    assert forbidden_script.scan_paths([path]) == []


def test_main_returns_0_on_committed_static_tree() -> None:
    assert forbidden_script.main([str(_STATIC_ROOT)]) == 0


def test_main_returns_1_on_dialog_violation(capsys: pytest.CaptureFixture[str]) -> None:
    path = _FIXTURES / "violation_dialog.html"
    assert forbidden_script.main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "violation_dialog.html:5:" in err
    assert "UX §7.12" in err


def test_main_returns_2_on_missing_explicit_path() -> None:
    assert forbidden_script.main(["/nonexistent/path.html"]) == 2


def test_cli_module_invocation() -> None:
    path = _FIXTURES / "violation_dialog.html"
    script = _REPO_ROOT / "scripts" / "check_dashboard_forbidden_patterns.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "violation_dialog.html" in proc.stderr

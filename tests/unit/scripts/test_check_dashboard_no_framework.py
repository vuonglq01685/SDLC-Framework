"""Unit tests for scripts/check_dashboard_no_framework.py (Story 5.4 AC4 / DD-08)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_no_framework as framework_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_framework"
_STATIC = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static"


def test_scan_flags_react_dependency_in_package_json() -> None:
    path = _FIXTURES / "violation_package.json"
    violations = framework_script.scan_package_json(path)
    assert violations
    assert "react" in violations[0].pattern


def test_scan_flags_react_min_js_vendor_bundle(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    bundle = vendor / "react.min.js"
    bundle.write_text("// react\n", encoding="utf-8")
    violations = framework_script.scan_static_tree(tmp_path)
    assert violations
    assert "react.min.js" in violations[0].pattern


def test_shipped_static_tree_passes_dd08_gate() -> None:
    assert _STATIC.is_dir(), "dashboard static root must exist"
    assert framework_script.scan_static_tree(_STATIC) == []


def test_main_returns_1_on_package_json_violation(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text('{"dependencies":{"vue":"^3.0.0"}}\n', encoding="utf-8")
    assert framework_script.main([str(pkg)]) == 1


def test_main_returns_0_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>\n", encoding="utf-8")
    assert framework_script.main([str(tmp_path)]) == 0


def test_violation_names_import(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text('{"dependencies":{"svelte":"^4.0.0"}}\n', encoding="utf-8")
    assert framework_script.main([str(pkg)]) == 1
    err = capsys.readouterr().err
    assert "svelte" in err


def test_chartjs_min_js_is_permitted(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "chart.min.js").write_text("// chart\n", encoding="utf-8")
    assert framework_script.scan_static_tree(tmp_path) == []


def test_cli_module_invocation(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text('{"dependencies":{"react":"18"}}\n', encoding="utf-8")
    script = _REPO_ROOT / "scripts" / "check_dashboard_no_framework.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(pkg)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "react" in proc.stderr or "react" in proc.stdout


# ── PAT-4 (DEC-1 opt-b): broadened bundle detection — any .js/.css with a
# framework-name token, not only `*.min.js` (closes the rename bypass) ──


def test_scan_flags_nonmin_react_bundle(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "react.js").write_text("// react\n", encoding="utf-8")
    violations = framework_script.scan_static_tree(tmp_path)
    assert violations
    assert "react.js" in violations[0].pattern


def test_scan_flags_vue_global_bundle(tmp_path: Path) -> None:
    (tmp_path / "vue.global.js").write_text("// vue\n", encoding="utf-8")
    violations = framework_script.scan_static_tree(tmp_path)
    assert violations
    assert "vue.global.js" in violations[0].pattern


def test_scan_flags_tailwind_css_bundle(tmp_path: Path) -> None:
    (tmp_path / "tailwind.css").write_text("/* tw */\n", encoding="utf-8")
    violations = framework_script.scan_static_tree(tmp_path)
    assert violations
    assert "tailwind.css" in violations[0].pattern


def test_marker_substring_does_not_false_positive(tmp_path: Path) -> None:
    # 'split.js' contains 'lit' as a raw substring but not as a name token —
    # boundary matching must NOT flag it (nor the dashboard's own scripts).
    (tmp_path / "split.js").write_text("// app\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("// app\n", encoding="utf-8")
    assert framework_script.scan_static_tree(tmp_path) == []


def test_plain_chartjs_is_permitted(tmp_path: Path) -> None:
    (tmp_path / "chart.js").write_text("// chart\n", encoding="utf-8")
    assert framework_script.scan_static_tree(tmp_path) == []


# ── PAT-1: no duplicate violations / no parent-tree re-walk on flat file lists
# (the exact input the no-arg CI/pre-commit invocation produces) ──


def test_scan_paths_no_duplicate_violations(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "react.min.js").write_text("// react\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"18"}}\n', encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>\n", encoding="utf-8")
    flat = [p for p in sorted(tmp_path.rglob("*")) if p.is_file()]
    violations = framework_script.scan_paths(flat)
    patterns = [v.pattern for v in violations]
    assert patterns.count("react") == 1
    assert sum("react.min.js" in p for p in patterns) == 1
    assert len(violations) == 2


# ── PAT-3: honest line number (real source line, not the alpha-sort index) ──


def test_package_json_violation_reports_real_line(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{\n  "name": "x",\n  "dependencies": {\n    "react": "18"\n  }\n}\n',
        encoding="utf-8",
    )
    violations = framework_script.scan_package_json(pkg)
    assert violations
    assert violations[0].line == 4  # the line where "react" actually appears


# ── PAT-5 (DEC-2 opt-b): default scan root is the dashboard dir so a
# dashboard-root package.json (outside static/) is covered ──


def test_default_root_is_dashboard_dir() -> None:
    assert framework_script._DEFAULT_ROOT.name == "dashboard"


def test_main_no_args_scans_clean_default_tree() -> None:
    assert framework_script.main([]) == 0


def test_dashboard_root_package_json_is_caught(tmp_path: Path) -> None:
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"18"}}\n', encoding="utf-8")
    assert framework_script.main([str(tmp_path)]) == 1

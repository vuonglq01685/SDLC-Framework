"""Unit tests for scripts/check_dashboard_no_data_theme.py (Story 5.2 AC3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_no_data_theme as theme_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_css"
_TOKENS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "styles" / "tokens.css"


def test_scan_file_flags_data_theme_selector() -> None:
    path = _FIXTURES / "violation_data_theme.css"
    violations = theme_script.scan_paths([path])
    assert violations
    assert violations[0].path == path
    assert "data-theme" in violations[0].pattern


def test_scan_file_clean_when_no_data_theme() -> None:
    path = _FIXTURES / "clean_component.css"
    assert theme_script.scan_paths([path]) == []


def test_tokens_css_passes_dd09_gate() -> None:
    assert _TOKENS.is_file(), "tokens.css must exist for GREEN path"
    assert theme_script.scan_paths([_TOKENS]) == []


def test_main_returns_1_on_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text('[data-theme="light"] { color: red; }\n', encoding="utf-8")
    assert theme_script.main([str(bad)]) == 1


def test_main_returns_0_on_clean(tmp_path: Path) -> None:
    good = tmp_path / "good.css"
    good.write_text(":root { --ink: var(--paper); }\n", encoding="utf-8")
    assert theme_script.main([str(good)]) == 0


def test_violation_reports_file_and_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text("x { }\n[data-theme] { }\n", encoding="utf-8")
    assert theme_script.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "bad.css" in err
    assert ":2:" in err


def test_js_dataset_theme_violation(tmp_path: Path) -> None:
    bad = tmp_path / "app.js"
    bad.write_text("document.body.dataset.theme = 'dark';\n", encoding="utf-8")
    violations = theme_script.scan_paths([bad])
    assert violations
    assert violations[0].line == 1


def test_cli_module_invocation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text('[data-theme="dark"] {}\n', encoding="utf-8")
    script = _REPO_ROOT / "scripts" / "check_dashboard_no_data_theme.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(bad)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "data-theme" in proc.stderr.lower() or "data-theme" in proc.stdout.lower()


# --- Review patches (bmad-code-review 2026-06-23) ---


def test_non_utf8_file_does_not_crash_and_still_flags(tmp_path: Path) -> None:
    """P1: a non-UTF-8 byte must not raise UnicodeDecodeError; the selector still flags."""
    bad = tmp_path / "bad.css"
    bad.write_bytes(b"[data-theme] { color: \xff; }\n")
    violations = theme_script.scan_paths([bad])
    assert violations
    assert violations[0].line == 1


def test_multiline_comment_preserves_violation_line(tmp_path: Path) -> None:
    """P2: a violation after a multi-line comment must report the correct source line."""
    bad = tmp_path / "bad.css"
    bad.write_text("/* a\n b\n c */\n[data-theme] { }\n", encoding="utf-8")
    violations = theme_script.scan_paths([bad])
    assert violations
    assert violations[0].line == 4


def test_whitespace_inside_attribute_selector_flags(tmp_path: Path) -> None:
    """P3a: the CSS-valid spaced form ``[ data-theme ]`` must be caught."""
    bad = tmp_path / "bad.css"
    bad.write_text("[ data-theme ] { }\n", encoding="utf-8")
    assert theme_script.scan_paths([bad])


def test_js_dataset_bracket_access_flags(tmp_path: Path) -> None:
    """P3b: ``dataset['theme']`` bracket access must be caught."""
    bad = tmp_path / "app.js"
    bad.write_text("el.dataset['theme'] = 'dark';\n", encoding="utf-8")
    assert theme_script.scan_paths([bad])


def test_js_getattribute_reports_specific_label(tmp_path: Path) -> None:
    """P3c: specific patterns must win over the bare catch-all (correct label, no dead code)."""
    bad = tmp_path / "app.js"
    bad.write_text("el.getAttribute('data-theme');\n", encoding="utf-8")
    violations = theme_script.scan_paths([bad])
    assert violations
    assert violations[0].pattern == "getAttribute(data-theme)"


def test_missing_explicit_path_is_not_silent_clean(tmp_path: Path) -> None:
    """P4: an explicit path that does not exist must not report a clean pass."""
    missing = tmp_path / "does_not_exist.css"
    assert theme_script.main([str(missing)]) == 2


def test_html_attribute_data_theme_flags(tmp_path: Path) -> None:
    """P5: a ``data-theme`` attribute in an ``.html`` asset must be caught."""
    bad = tmp_path / "index.html"
    bad.write_text('<html data-theme="dark"><body></body></html>\n', encoding="utf-8")
    assert theme_script.scan_paths([bad])


def test_html_inline_script_dataset_theme_flags(tmp_path: Path) -> None:
    """P5: an inline ``<script>`` theme write in an ``.html`` asset must be caught."""
    bad = tmp_path / "index.html"
    bad.write_text("<script>document.body.dataset.theme = 'dark';</script>\n", encoding="utf-8")
    assert theme_script.scan_paths([bad])


def test_html_fixture_flags() -> None:
    """P5: the ``.html`` RED fixture must fail the gate."""
    fixture = _FIXTURES / "violation_html_data_theme.html"
    assert theme_script.scan_paths([fixture])


def test_shipped_index_html_passes_gate() -> None:
    """P5 GREEN: the real shipped index.html must stay clean under the extended gate."""
    index = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "index.html"
    if index.is_file():
        assert theme_script.scan_paths([index]) == []

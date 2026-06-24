"""Unit tests for scripts/check_dashboard_no_external_fonts.py (Story 5.3 AC1 / DD-10)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_no_external_fonts as fonts_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_css"
_INDEX = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "index.html"
_TOKENS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "styles" / "tokens.css"


def test_scan_flags_google_fonts_link() -> None:
    path = _FIXTURES / "violation_google_fonts.html"
    violations = fonts_script.scan_paths([path])
    assert violations
    assert "fonts.googleapis.com" in violations[0].pattern


def test_scan_clean_when_self_hosted_only() -> None:
    path = _FIXTURES / "clean_component.css"
    assert fonts_script.scan_paths([path]) == []


def test_shipped_index_and_tokens_pass_dd10_gate() -> None:
    paths = [p for p in (_INDEX, _TOKENS) if p.is_file()]
    assert paths, "shipped dashboard assets must exist for GREEN path"
    assert fonts_script.scan_paths(paths) == []


def test_main_returns_1_on_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.html"
    bad.write_text(
        '<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">\n',
        encoding="utf-8",
    )
    assert fonts_script.main([str(bad)]) == 1


def test_main_returns_0_on_clean(tmp_path: Path) -> None:
    good = tmp_path / "good.html"
    good.write_text('<link rel="stylesheet" href="/static/styles/tokens.css">\n', encoding="utf-8")
    assert fonts_script.main([str(good)]) == 0


def test_violation_reports_file_line_col(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / "bad.html"
    bad.write_text(
        "x\n<link href='https://fonts.gstatic.com/s/inter.woff2'>\n",
        encoding="utf-8",
    )
    assert fonts_script.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "bad.html" in err
    assert ":2:" in err


def test_cli_module_invocation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.html"
    bad.write_text('<link href="https://fonts.googleapis.com/css">\n', encoding="utf-8")
    script = _REPO_ROOT / "scripts" / "check_dashboard_no_external_fonts.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(bad)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "fonts.googleapis.com" in proc.stderr or "fonts.googleapis.com" in proc.stdout

"""CSS gate tests for dashboard design tokens (Story 5.2 AC2, AC3)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STYLES = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "styles"
_CONFIG = _STYLES / ".stylelintrc.json"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_css"


def _npx_available() -> bool:
    return shutil.which("npx") is not None


def _run_stylelint(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "npx",
            "--yes",
            "stylelint@16.18.0",
            str(target),
            "--config",
            str(_CONFIG),
            "--allow-empty-input",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(not _npx_available(), reason="npx not available")
def test_stylelint_red_fixture_fails_on_raw_literals() -> None:
    proc = _run_stylelint(_FIXTURES / "violation_raw_literals.css")
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "violation_raw_literals.css" in combined


@pytest.mark.skipif(not _npx_available(), reason="npx not available")
def test_stylelint_green_fixture_passes_with_var_references() -> None:
    proc = _run_stylelint(_FIXTURES / "clean_component.css")
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.skipif(not _npx_available(), reason="npx not available")
def test_stylelint_tokens_css_is_canonical_source_of_raw_values() -> None:
    proc = _run_stylelint(_STYLES / "tokens.css")
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.skipif(not _npx_available(), reason="npx not available")
def test_stylelint_reports_line_column_on_violation() -> None:
    proc = _run_stylelint(_FIXTURES / "violation_raw_literals.css")
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert ":" in combined  # file:line:column stylelint default formatter

"""Unit tests for scripts/check_dashboard_motion.py (Story 5.4 AC2 / DD-14)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_dashboard_motion as motion_script

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "dashboard_css"
_FOCUS_MOTION = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "styles" / "focus-motion.css"
_TOKENS = _REPO_ROOT / "src" / "sdlc" / "dashboard" / "static" / "styles" / "tokens.css"


def test_scan_flags_transition_declaration() -> None:
    path = _FIXTURES / "violation_transition.css"
    violations = motion_script.scan_paths([path])
    assert violations
    assert "transition:" in violations[0].pattern


def test_scan_flags_non_pulse_keyframes() -> None:
    path = _FIXTURES / "violation_keyframes_spin.css"
    violations = motion_script.scan_paths([path])
    labels = {v.pattern for v in violations}
    assert "@keyframes spin" in labels


def test_scan_clean_pulse_component_passes() -> None:
    path = _FIXTURES / "clean_pulse_component.css"
    assert motion_script.scan_paths([path]) == []


def test_tokens_css_passes_dd14_gate() -> None:
    assert _TOKENS.is_file(), "tokens.css must exist for GREEN path"
    assert motion_script.scan_paths([_TOKENS]) == []


def test_focus_motion_css_passes_dd14_gate() -> None:
    assert _FOCUS_MOTION.is_file(), "focus-motion.css must exist for GREEN path"
    assert motion_script.scan_paths([_FOCUS_MOTION]) == []


def test_main_returns_1_on_transition_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text(".x { transition: width 0.2s; }\n", encoding="utf-8")
    assert motion_script.main([str(bad)]) == 1


def test_main_returns_0_on_clean_pulse(tmp_path: Path) -> None:
    good = tmp_path / "good.css"
    good.write_text(".dot { animation: pulse var(--motion-pulse-live); }\n", encoding="utf-8")
    assert motion_script.main([str(good)]) == 0


def test_violation_reports_file_line_col(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text("a { }\n  transition: opacity 1s;\n", encoding="utf-8")
    assert motion_script.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "bad.css" in err
    assert ":2:" in err


def test_reduced_motion_animation_none_is_allowed(tmp_path: Path) -> None:
    css = tmp_path / "motion.css"
    css.write_text(
        "@media (prefers-reduced-motion: reduce) {\n  .live-dot-pulse { animation: none; }\n}\n",
        encoding="utf-8",
    )
    assert motion_script.scan_paths([css]) == []


def test_cli_module_invocation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.css"
    bad.write_text("@keyframes fade { from { opacity: 0; } }\n", encoding="utf-8")
    script = _REPO_ROOT / "scripts" / "check_dashboard_motion.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(bad)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "keyframes" in proc.stderr.lower() or "keyframes" in proc.stdout.lower()

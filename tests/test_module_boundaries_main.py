"""Integration tests for scripts/check_module_boundaries.py.

Covers check_loc_cap (LOC-cap discipline + path-prefix exemption), the main()
entrypoint (clean / boundary / LOC / relative-import paths), self-compliance
of the validator against its own source, and a baseline test for the
specialist-validator placeholder. Core boundary-logic tests live in
tests/test_check_module_boundaries.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import check_module_boundaries as mb

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# check_loc_cap — boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loc_cap_passes_for_file_under_400(tmp_path: Path) -> None:
    f = tmp_path / "ok.py"
    f.write_text("\n".join("x = 1" for _ in range(399)) + "\n")
    assert mb.check_loc_cap(f) == []


@pytest.mark.unit
def test_loc_cap_passes_exactly_at_400(tmp_path: Path) -> None:
    f = tmp_path / "exact.py"
    f.write_text("\n".join("x = 1" for _ in range(400)) + "\n")
    assert mb.check_loc_cap(f) == []


@pytest.mark.unit
def test_loc_cap_fails_at_401(tmp_path: Path) -> None:
    f = tmp_path / "big.py"
    f.write_text("\n".join("x = 1" for _ in range(401)) + "\n")
    violations = mb.check_loc_cap(f)
    assert len(violations) == 1
    assert "401 lines" in violations[0]
    assert "cap: 400" in violations[0]
    assert "Architecture §765" in violations[0]


@pytest.mark.unit
def test_loc_cap_no_trailing_newline_at_400(tmp_path: Path) -> None:
    """400 content lines with no trailing newline -> exactly 400 lines (passes)."""
    f = tmp_path / "no_trailing.py"
    f.write_text("\n".join("x = 1" for _ in range(400)))
    assert mb.check_loc_cap(f) == []


@pytest.mark.unit
def test_loc_cap_no_trailing_newline_at_401(tmp_path: Path) -> None:
    f = tmp_path / "no_trailing_over.py"
    f.write_text("\n".join("x = 1" for _ in range(401)))
    violations = mb.check_loc_cap(f)
    assert len(violations) == 1
    assert "401 lines" in violations[0]


@pytest.mark.unit
def test_loc_cap_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.py"
    f.write_text("")
    assert mb.check_loc_cap(f) == []


@pytest.mark.unit
def test_loc_cap_returns_empty_for_nonexistent_file(tmp_path: Path) -> None:
    f = tmp_path / "does_not_exist.py"
    assert mb.check_loc_cap(f) == []


# ---------------------------------------------------------------------------
# check_loc_cap — fixture exemption (P4: Path semantics)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loc_cap_exempts_tests_fixtures_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relative path under tests/fixtures/ is exempt (P9: monkeypatch.chdir)."""
    monkeypatch.chdir(tmp_path)
    fixtures_path = Path("tests/fixtures")
    fixtures_path.mkdir(parents=True)
    seed = fixtures_path / "big_seed.py"
    seed.write_text("\n".join("x = 1" for _ in range(500)) + "\n")
    assert mb.check_loc_cap(seed) == []


@pytest.mark.unit
def test_loc_cap_exempts_tests_fixtures_absolute(tmp_path: Path) -> None:
    """Absolute path under .../tests/fixtures/ is also exempt (P4)."""
    fixtures_path = tmp_path / "tests" / "fixtures"
    fixtures_path.mkdir(parents=True)
    seed = fixtures_path / "big_seed.py"
    seed.write_text("\n".join("x = 1" for _ in range(500)) + "\n")
    assert mb.check_loc_cap(seed) == []


# ---------------------------------------------------------------------------
# main() — exit codes + violation reporting
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_main_returns_0_for_clean_files(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text("from __future__ import annotations\n\nx = 1\n")
    assert mb.main([str(f)]) == 0


@pytest.mark.unit
def test_main_returns_1_for_loc_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "big.py"
    f.write_text("\n".join("x = 1" for _ in range(401)) + "\n")
    assert mb.main([str(f)]) == 1
    assert "LOC cap exceeded" in capsys.readouterr().err


@pytest.mark.unit
def test_main_skips_non_py_files(tmp_path: Path) -> None:
    f = tmp_path / "readme.md"
    f.write_text("# Hello\n")
    assert mb.main([str(f)]) == 0


@pytest.mark.unit
def test_main_skips_nonexistent_paths() -> None:
    assert mb.main(["/does/not/exist.py"]) == 0


@pytest.mark.unit
def test_main_reports_boundary_violation_for_src_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sdlc_root = tmp_path / "src" / "sdlc"
    state_dir = sdlc_root / "state"
    state_dir.mkdir(parents=True)
    f = state_dir / "probe.py"
    f.write_text("from __future__ import annotations\nfrom sdlc.engine import auto_loop\n")
    monkeypatch.setattr(mb, "SDLC_ROOT", sdlc_root)
    assert mb.main([str(f)]) == 1
    err = capsys.readouterr().err
    assert "state/ -> engine/" in err
    # Hybrid wording must list the full forbidden set
    assert "engine/" in err and "dispatcher/" in err and "runtime/" in err


@pytest.mark.unit
def test_main_reports_relative_import_in_src_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: relative import inside a src/sdlc/<module>/ file fires §1075."""
    sdlc_root = tmp_path / "src" / "sdlc"
    state_dir = sdlc_root / "state"
    state_dir.mkdir(parents=True)
    f = state_dir / "rel.py"
    f.write_text("from __future__ import annotations\nfrom . import atomic\n")
    monkeypatch.setattr(mb, "SDLC_ROOT", sdlc_root)
    assert mb.main([str(f)]) == 1
    err = capsys.readouterr().err
    assert "relative import" in err
    assert "§1075" in err


@pytest.mark.unit
def test_main_reports_from_sdlc_import_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end check that `from sdlc import engine` no longer bypasses (P2)."""
    sdlc_root = tmp_path / "src" / "sdlc"
    state_dir = sdlc_root / "state"
    state_dir.mkdir(parents=True)
    f = state_dir / "probe.py"
    f.write_text("from __future__ import annotations\nfrom sdlc import engine\n")
    monkeypatch.setattr(mb, "SDLC_ROOT", sdlc_root)
    assert mb.main([str(f)]) == 1
    assert "state/ -> engine/" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Self-compliance + LOC cap on the validator script itself
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validator_script_self_compliance() -> None:
    """The validator must pass when run over its own source (AC3 self-discipline)."""
    script = REPO_ROOT / "scripts" / "check_module_boundaries.py"
    assert script.exists()
    # File-to-module returns None for files outside src/sdlc/, so this exercises
    # the LOC-cap path on the script itself.
    assert mb.check_loc_cap(script) == []


@pytest.mark.unit
def test_validator_script_under_400_loc() -> None:
    """Hard guard: validator stays under the cap it enforces."""
    script = REPO_ROOT / "scripts" / "check_module_boundaries.py"
    text = script.read_text(encoding="utf-8")
    lines = text.count("\n") + (0 if text.endswith("\n") or text == "" else 1)
    assert lines <= mb.LOC_CAP, f"validator is {lines} lines (cap {mb.LOC_CAP})"


# ---------------------------------------------------------------------------
# specialist-validator placeholder (AC5 baseline)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_specialists_exits_zero_with_placeholder_message() -> None:
    """`scripts/validate_specialists.py` is the v0.2 no-op (AC5)."""
    script = REPO_ROOT / "scripts" / "validate_specialists.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "v0.2 placeholder" in proc.stdout
    assert "Story 2A-2" in proc.stdout

"""Unit tests for check_no_direct_state_writes.py linter (AC3, Story 1.10)."""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

import check_no_direct_state_writes as linter  # noqa: E402

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_no_direct_state_writes.py"
_SRC_ATOMIC = Path(__file__).parent.parent.parent / "src" / "sdlc" / "state" / "atomic.py"


def _run_linter(
    content: str, tmp_path: Path, filename: str = "test_subject.py"
) -> subprocess.CompletedProcess[str]:
    """Write content to a temp .py file and run the linter on it."""
    target = tmp_path / filename
    target.write_text(content, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Banned patterns — expect exit 1
# ---------------------------------------------------------------------------


def test_open_state_json_w_mode_flagged(tmp_path: Path) -> None:
    result = _run_linter('f = open("path/to/state.json", "w")\n', tmp_path)
    assert result.returncode == 1
    assert "direct state write detected" in result.stderr


def test_open_state_json_wb_mode_flagged(tmp_path: Path) -> None:
    result = _run_linter('f = open("state.json", "wb")\n', tmp_path)
    assert result.returncode == 1


def test_open_state_path_var_flagged(tmp_path: Path) -> None:
    result = _run_linter('open(STATE_PATH, "w")\n', tmp_path)
    assert result.returncode == 1


def test_path_write_text_state_json_flagged(tmp_path: Path) -> None:
    result = _run_linter('from pathlib import Path\nPath("state.json").write_text("x")\n', tmp_path)
    assert result.returncode == 1
    assert "direct state write detected" in result.stderr


def test_os_replace_state_json_flagged(tmp_path: Path) -> None:
    result = _run_linter('import os\nos.replace("tmp", "state.json")\n', tmp_path)
    assert result.returncode == 1
    assert "direct state write detected" in result.stderr


def test_os_rename_state_json_flagged(tmp_path: Path) -> None:
    result = _run_linter('import os\nos.rename("tmp", "state.json")\n', tmp_path)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Allowed patterns — expect exit 0
# ---------------------------------------------------------------------------


def test_open_state_json_r_mode_not_flagged(tmp_path: Path) -> None:
    result = _run_linter('f = open("state.json", "r")\n', tmp_path)
    assert result.returncode == 0


def test_open_unrelated_file_w_mode_not_flagged(tmp_path: Path) -> None:
    result = _run_linter('f = open("output.json", "w")\n', tmp_path)
    assert result.returncode == 0


def test_comparison_expression_not_flagged(tmp_path: Path) -> None:
    result = _run_linter('x = "state.json" == path\n', tmp_path)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Escape-hatch tests (noqa: state-write)
# ---------------------------------------------------------------------------


def test_noqa_with_reason_silences(tmp_path: Path) -> None:
    code = 'f = open("state.json", "w")  # noqa: state-write -- delegated to migration script\n'
    result = _run_linter(code, tmp_path)
    assert result.returncode == 0


def test_noqa_with_em_dash_reason_silences(tmp_path: Path) -> None:
    code = 'f = open("state.json", "w")  # noqa: state-write — delegated to migration script\n'
    result = _run_linter(code, tmp_path)
    assert result.returncode == 0


def test_noqa_without_reason_flagged(tmp_path: Path) -> None:
    code = 'f = open("state.json", "w")  # noqa: state-write\n'
    result = _run_linter(code, tmp_path)
    assert result.returncode == 1
    assert "requires a reason" in result.stderr


def test_noqa_short_reason_flagged(tmp_path: Path) -> None:
    # Reason must be ≥ 10 chars; "short" is only 5
    code = 'f = open("state.json", "w")  # noqa: state-write -- short\n'
    result = _run_linter(code, tmp_path)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Exempt directories
# ---------------------------------------------------------------------------


def test_exempt_dir_not_scanned(tmp_path: Path) -> None:
    """Files under exempt dirs must not be flagged even if they contain banned patterns."""
    # Create a file that looks like it's in tests/ (exempt)
    # But since we're passing the path directly, we need to verify exemption by path segment
    # The linter exempts based on first path segment relative to repo root.
    # Since we pass a tmp_path file, it won't be exempt. This test uses the fixture instead.
    fixture = (
        Path(__file__).parent.parent / "fixtures" / "lint_negative" / "direct_state_write.py.txt"
    )
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(fixture)],
        capture_output=True,
        text=True,
        check=False,
    )
    # The .py.txt file won't match *.py glob; but even if passed directly, it's under tests/
    # which is an exempt dir — so linter should return 0
    assert result.returncode == 0


def test_self_exempt_atomic_py() -> None:
    """src/sdlc/state/atomic.py must return exit 0 (self-exempt canonical writer)."""
    if not _SRC_ATOMIC.exists():
        pytest.skip("atomic.py not yet created")
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(_SRC_ATOMIC)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"atomic.py must be self-exempt but got violations:\n{result.stderr}"
    )


def test_self_exempt_atomic_py_only(tmp_path: Path) -> None:
    """Only atomic.py is self-exempt; other state/ files are NOT exempt."""
    # Create a fake state/model-like file that contains a banned pattern
    code = textwrap.dedent("""\
        import os
        os.replace("tmp", "state.json")
    """)
    # This file is in tmp_path (not under any exempt dir), so it should be flagged
    result = _run_linter(code, tmp_path, "state_other.py")
    assert result.returncode == 1, "Non-atomic state files must not be self-exempt"


# ---------------------------------------------------------------------------
# No violations on clean codebase
# ---------------------------------------------------------------------------


def test_clean_src_sdlc_has_no_violations() -> None:
    """The current src/sdlc/ tree must have zero state-write violations."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Expected 0 violations in src/sdlc/ but got:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Direct in-process tests — cover the module's internal API for 90% coverage
# ---------------------------------------------------------------------------


class TestVisitorDirect:
    """In-process tests exercising _Visitor, _scan_file, and helpers directly."""

    def _parse_violations(self, code: str) -> list[tuple[int, str]]:
        tree = ast.parse(code)
        v = linter._Visitor()
        v.visit(tree)
        return v.violations

    def test_open_state_json_w_returns_violation(self) -> None:
        violations = self._parse_violations('open("state.json", "w")')
        assert len(violations) == 1
        assert "open()" in violations[0][1]

    def test_open_wb_mode_returns_violation(self) -> None:
        violations = self._parse_violations('open("state.json", "wb")')
        assert len(violations) == 1

    def test_open_r_mode_no_violation(self) -> None:
        violations = self._parse_violations('open("state.json", "r")')
        assert violations == []

    def test_open_unrelated_file_no_violation(self) -> None:
        violations = self._parse_violations('open("output.json", "w")')
        assert violations == []

    def test_path_write_text_state_json_violation(self) -> None:
        violations = self._parse_violations('Path("state.json").write_text("x")')
        assert len(violations) == 1
        assert "write_text" in violations[0][1]

    def test_path_write_bytes_state_json_violation(self) -> None:
        violations = self._parse_violations('Path("state.json").write_bytes(b"x")')
        assert len(violations) == 1

    def test_os_replace_state_json_violation(self) -> None:
        violations = self._parse_violations('os.replace("tmp", "state.json")')
        assert len(violations) == 1

    def test_os_rename_state_json_violation(self) -> None:
        violations = self._parse_violations('os.rename("tmp", "state.json")')
        assert len(violations) == 1

    def test_scan_file_valid_noqa(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.py"
        f.write_text('open("state.json","w")  # noqa: state-write -- legacy migration\n')
        assert linter._scan_file(f) == []

    def test_scan_file_bare_noqa_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text('open("state.json","w")  # noqa: state-write\n')
        results = linter._scan_file(f)
        assert len(results) == 1
        assert "requires a reason" in results[0][1]

    def test_scan_file_oserror_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.py"
        assert linter._scan_file(missing) == []

    def test_scan_file_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.py"
        f.write_text("def (\n")
        assert linter._scan_file(f) == []

    def test_is_exempt_scripts_dir(self) -> None:
        script_file = Path(__file__).parent.parent.parent / "scripts" / "anything.py"
        assert linter._is_exempt(script_file)

    def test_is_exempt_atomic_py(self) -> None:
        atomic = Path(__file__).parent.parent.parent / "src" / "sdlc" / "state" / "atomic.py"
        assert linter._is_exempt(atomic)

    def test_is_exempt_non_exempt_src_file(self) -> None:
        src_file = Path(__file__).parent.parent.parent / "src" / "sdlc" / "ids" / "builders.py"
        assert not linter._is_exempt(src_file)

    def test_expand_targets_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        result = linter._expand_targets([str(tmp_path)])
        assert len(result) == 2

    def test_expand_targets_file(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text("")
        result = linter._expand_targets([str(f)])
        assert result == [f]

    def test_main_returns_0_on_clean_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n")
        rc = linter.main([str(f)])
        assert rc == 0

    def test_main_returns_1_on_violation(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text('open("state.json","w")\n')
        rc = linter.main([str(f)])
        assert rc == 1

    def test_filter_violations_by_noqa_em_dash(self) -> None:
        violations = [(1, "open() with write mode on state path")]
        lines = ['open("state.json","w")  # noqa: state-write — migration\n']
        result = linter._filter_violations_by_noqa(violations, lines)
        assert result == []

    def test_find_bare_noqa_on_non_violation_line(self) -> None:
        lines = ["x = 1  # noqa: state-write\n"]
        results = linter._find_bare_noqa(lines, [])
        assert len(results) == 1
        assert "requires a reason" in results[0][1]

"""Unit tests for scripts/check_no_journal_mutation.py (AC3, Story 1.11).

Subprocess CLI tests live here. In-process ``_Visitor`` tests live in
``tests/unit/test_journal_mutation_validator_visitor.py``. Story 1.11 review-patch
additions for new detectors live in ``tests/unit/test_journal_mutation_validator_review.py``.
The split keeps each file ≤400 LOC (NFR-MAINT-3 / Architecture §765).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_no_journal_mutation.py"


def _run(code: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Write code to a temp .py file and run the linter against it."""
    src = tmp_path / "input.py"
    src.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(src)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# CLI tests: banned patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_open_journal_log_w_mode_flagged(tmp_path: Path) -> None:
    result = _run('open("path/to/journal.log", "w")', tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_open_journal_jsonl_a_mode_flagged(tmp_path: Path) -> None:
    result = _run('open("journal.jsonl", "a")', tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_open_journal_r_plus_mode_flagged(tmp_path: Path) -> None:
    result = _run('open("journal.log", "r+")', tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_path_write_text_journal_log_flagged(tmp_path: Path) -> None:
    result = _run('from pathlib import Path\nPath("journal.log").write_text("x")', tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_os_replace_journal_log_flagged(tmp_path: Path) -> None:
    result = _run('import os\nos.replace("/tmp/x.tmp", "journal.log")', tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_seek_then_write_same_handle_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def bad():
            f = open("/tmp/foo", "rb+")
            f.seek(0)
            f.write(b"x")
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


@pytest.mark.unit
def test_lseek_then_write_same_fd_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        import os
        def bad(fd):
            os.lseek(fd, 0, 0)
            os.write(fd, b"x")
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 1
    assert "journal mutation detected" in result.stderr


# ---------------------------------------------------------------------------
# CLI tests: clean patterns
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_open_journal_r_mode_not_flagged(tmp_path: Path) -> None:
    result = _run('open("journal.log", "r")', tmp_path)
    assert result.returncode == 0


@pytest.mark.unit
def test_seek_alone_not_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def read_it(f):
            f.seek(0)
            data = f.read()
            return data
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0


@pytest.mark.unit
def test_write_alone_not_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def write_it(f, data):
            f.write(data)
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0


@pytest.mark.unit
def test_seek_then_write_different_handles_not_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def mixed(f, g):
            f.seek(0)
            g.write(b"x")
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Escape hatch tests (suppress directives)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_noqa_with_reason_silences(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def patched():
            f = open("/tmp/foo", "rb+")
            f.seek(0)
            f.write(b"x")  # noqa: journal-mutation -- restoring backup snapshot in test fixture
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0


@pytest.mark.unit
def test_noqa_without_reason_flagged(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """\
        def bad():
            f = open("/tmp/foo", "rb+")
            f.seek(0)
            f.write(b"x")  # noqa: journal-mutation
        """
    )
    result = _run(code, tmp_path)
    assert result.returncode == 1
    assert "real violation" in result.stderr


# ---------------------------------------------------------------------------
# Exempt directories and self-exemptions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exempt_dir_not_scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Files under <repo_root>/tests/ are exempt — verify by patching ``_REPO_ROOT``.

    The linter's ``_is_exempt`` checks the first path segment relative to repo root, so
    we monkey-patch the module's ``_REPO_ROOT`` to ``tmp_path`` and place the violating
    file under ``tmp_path/tests/`` to make the exemption check fire (review fix).
    """
    sys.path.insert(0, str(_SCRIPT.parent.parent))
    from scripts import check_no_journal_mutation as linter  # type: ignore[import]

    monkeypatch.setattr(linter, "_REPO_ROOT", tmp_path)
    tests_sub = tmp_path / "tests"
    tests_sub.mkdir()
    bad_file = tests_sub / "bad.py"
    bad_file.write_text('open("journal.log", "w")', encoding="utf-8")
    # File would otherwise be flagged; exempt because tmp_path/tests/ is treated as repo
    # tests/ dir (first segment 'tests' is in _EXEMPT_DIRS).
    assert linter._is_exempt(bad_file), "tests/ dir under patched _REPO_ROOT must be exempt"
    assert linter.main([str(bad_file)]) == 0


@pytest.mark.unit
def test_self_exempt_writer_py() -> None:
    """src/sdlc/journal/writer.py is self-exempt — contains actual O_APPEND opens."""
    writer = Path(__file__).parent.parent.parent / "src" / "sdlc" / "journal" / "writer.py"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(writer)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"writer.py should be self-exempt:\n{result.stderr}"


@pytest.mark.unit
def test_reader_py_not_self_exempt_but_has_no_violations() -> None:
    """reader.py is NOT self-exempt but uses only read modes — should be clean."""
    reader = Path(__file__).parent.parent.parent / "src" / "sdlc" / "journal" / "reader.py"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(reader)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"reader.py should be clean:\n{result.stderr}"

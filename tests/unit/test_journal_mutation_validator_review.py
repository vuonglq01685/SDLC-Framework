"""Story 1.11 review-patch tests for ``scripts/check_no_journal_mutation.py``.

Lifted from ``test_journal_mutation_validator.py`` to keep that file ≤400 LOC
(NFR-MAINT-3 / Architecture §765). Covers the new detectors (os.open with write
flags, Path.open("w"), os.truncate, os.unlink, os.link, os.symlink, mode= kwarg,
os-alias lseek+write, module-level seek+write, no-double-flag of nested defs)
plus distinct stray-vs-violation noqa messaging and docstring-noqa exclusion.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_no_journal_mutation.py"


class TestReviewPatches:
    """In-process tests for the patches added during Story 1.11 code review."""

    def _linter(self) -> object:
        sys.path.insert(0, str(_SCRIPT.parent.parent))
        from scripts import check_no_journal_mutation as linter  # type: ignore[import]

        return linter

    def _visit(self, code: str) -> list[tuple[int, str]]:
        sys.path.insert(0, str(_SCRIPT.parent.parent))
        from scripts import check_no_journal_mutation as linter  # type: ignore[import]

        tree = ast.parse(textwrap.dedent(code))
        os_aliases = linter._collect_os_aliases(tree)
        v = linter._Visitor(os_aliases)
        v.visit(tree)
        module_top = ast.Module(
            body=[
                n
                for n in tree.body
                if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            ],
            type_ignores=[],
        )
        v.violations.extend(linter._find_seek_then_write_violations(module_top))
        v.violations.extend(linter._find_lseek_then_write_violations(module_top, os_aliases))
        return v.violations

    @pytest.mark.unit
    def test_visitor_os_open_with_write_flags(self) -> None:
        code = 'import os\nos.open("journal.log", os.O_WRONLY | os.O_TRUNC)\n'
        violations = self._visit(code)
        assert any("os.open()" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_os_open_read_only_not_flagged(self) -> None:
        code = 'import os\nos.open("journal.log", os.O_RDONLY)\n'
        violations = self._visit(code)
        assert violations == []

    @pytest.mark.unit
    def test_visitor_path_open_w_mode_flagged(self) -> None:
        violations = self._visit('Path("journal.log").open("w")')
        assert any("Path.open()" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_open_mode_kwarg_flagged(self) -> None:
        violations = self._visit('open("journal.log", mode="w")')
        assert any("open()" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_os_truncate_journal_flagged(self) -> None:
        violations = self._visit('import os\nos.truncate("journal.log", 0)')
        assert any("truncate" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_path_unlink_journal_flagged(self) -> None:
        violations = self._visit('Path("journal.log").unlink()')
        assert any("unlink" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_os_link_to_journal_flagged(self) -> None:
        violations = self._visit('import os\nos.link("/tmp/x", "journal.log")')
        assert any("link" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_os_symlink_to_journal_flagged(self) -> None:
        violations = self._visit('import os\nos.symlink("/tmp/x", "journal.log")')
        assert any("symlink" in m for _, m in violations)

    @pytest.mark.unit
    def test_visitor_module_level_seek_then_write(self) -> None:
        code = textwrap.dedent(
            """\
            f = open("/tmp/j", "rb+")
            f.seek(0)
            f.write(b"x")
            """
        )
        violations = self._visit(code)
        assert any("seek" in m.lower() for _, m in violations)

    @pytest.mark.unit
    def test_visitor_os_alias_lseek_write(self) -> None:
        code = textwrap.dedent(
            """\
            import os as _os
            def fn(fd):
                _os.lseek(fd, 0, 0)
                _os.write(fd, b"x")
            """
        )
        violations = self._visit(code)
        assert any("lseek" in m.lower() for _, m in violations)

    @pytest.mark.unit
    def test_visitor_nested_def_not_double_flagged(self) -> None:
        code = textwrap.dedent(
            """\
            def outer():
                f.seek(0)
                f.write(b"x")
                def inner():
                    g.seek(0)
                    g.write(b"y")
            """
        )
        violations = self._visit(code)
        assert len(violations) == 2

    @pytest.mark.unit
    def test_filter_violations_noqa_in_docstring_not_suppressed(self) -> None:
        """A noqa inside a docstring must NOT silence a real violation on another line."""
        sys.path.insert(0, str(_SCRIPT.parent.parent))
        from scripts import check_no_journal_mutation as linter  # type: ignore[import]

        code = textwrap.dedent(
            '''\
            """Docstring with # noqa: journal-mutation -- this is the docstring text."""
            open("journal.log", "w")
            '''
        )
        tree = ast.parse(code)
        lines = code.splitlines()
        os_aliases = linter._collect_os_aliases(tree)
        v = linter._Visitor(os_aliases)
        v.visit(tree)
        string_lines = linter._string_literal_linenos(tree)
        result = linter._filter_violations_by_noqa(v.violations, lines, string_lines)
        assert any(ln == 2 for ln, _ in result)

    @pytest.mark.unit
    def test_is_exempt_writer_py_via_posix(self) -> None:
        linter = self._linter()
        writer = _SCRIPT.parent.parent / "src" / "sdlc" / "journal" / "writer.py"
        assert linter._is_exempt(writer)

    @pytest.mark.unit
    def test_assert_canonical_api_holds(self) -> None:
        linter = self._linter()
        linter._assert_canonical_api()

    @pytest.mark.unit
    def test_bare_noqa_alone_uses_distinct_message(self) -> None:
        linter = self._linter()
        lines = ["x = 1  # noqa: journal-mutation"]
        result = linter._find_bare_noqa(lines, existing=[])
        assert len(result) == 1
        assert "stray" in result[0][1].lower()

    @pytest.mark.unit
    def test_violation_with_bare_noqa_uses_violation_message(self) -> None:
        linter = self._linter()
        violations = [(1, "open() with mode 'w' on journal path")]
        lines = ['open("journal.log", "w")  # noqa: journal-mutation']
        result = linter._filter_violations_by_noqa(violations, lines)
        assert len(result) == 1
        assert "real violation" in result[0][1].lower()

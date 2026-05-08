"""In-process AST-visitor tests for ``check_no_journal_mutation.py`` (>=95% coverage).

Lifted from ``test_journal_mutation_validator.py`` to keep that file ≤400 LOC
(NFR-MAINT-3 / Architecture §765). These tests exercise visitor internals without
subprocess overhead — important on Windows where subprocess multiprocessing semantics
differ from POSIX.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_no_journal_mutation.py"


class TestVisitorDirect:
    """Direct AST-walk tests for ``scripts/check_no_journal_mutation.py``."""

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
    def test_visitor_open_w_on_journal_path(self) -> None:
        violations = self._visit('open("journal.log", "w")')
        assert len(violations) == 1
        assert "open()" in violations[0][1]

    @pytest.mark.unit
    def test_visitor_open_rb_plus_on_journal_path(self) -> None:
        violations = self._visit('open("journal_path", "rb+")')
        assert len(violations) == 1

    @pytest.mark.unit
    def test_visitor_open_read_mode_no_violation(self) -> None:
        violations = self._visit('open("journal.log", "r")')
        assert violations == []

    @pytest.mark.unit
    def test_visitor_path_write_bytes_on_journal(self) -> None:
        violations = self._visit('Path("journal.jsonl").write_bytes(b"x")')
        assert len(violations) == 1
        assert "write_bytes" in violations[0][1]

    @pytest.mark.unit
    def test_visitor_os_rename_journal_dst(self) -> None:
        violations = self._visit('os.rename("/tmp/x", "journal.log")')
        assert len(violations) == 1
        assert "rename" in violations[0][1]

    @pytest.mark.unit
    def test_visitor_seek_write_same_receiver(self) -> None:
        code = """\
            def fn():
                f.seek(0)
                f.write(b"x")
        """
        violations = self._visit(code)
        assert len(violations) == 1
        assert "seek" in violations[0][1].lower()

    @pytest.mark.unit
    def test_visitor_lseek_write_same_fd(self) -> None:
        code = """\
            def fn(fd):
                os.lseek(fd, 0, 0)
                os.write(fd, b"x")
        """
        violations = self._visit(code)
        assert len(violations) == 1
        assert "lseek" in violations[0][1].lower()

    @pytest.mark.unit
    def test_visitor_seek_different_handles_no_violation(self) -> None:
        code = """\
            def fn(f, g):
                f.seek(0)
                g.write(b"x")
        """
        violations = self._visit(code)
        assert violations == []

    @pytest.mark.unit
    def test_visitor_no_violation_on_open_journal_r(self) -> None:
        violations = self._visit('open("journal.log", "r")')
        assert violations == []

    @pytest.mark.unit
    def test_filter_violations_noqa_with_reason_suppresses(self) -> None:
        linter = self._linter()
        violations = [(1, "open() with mode 'w' on journal path")]
        lines = ['open("journal.log", "w")  # noqa: journal-mutation -- test fixture cleanup']
        result = linter._filter_violations_by_noqa(violations, lines)
        assert result == []

    @pytest.mark.unit
    def test_filter_violations_bare_noqa_flagged(self) -> None:
        linter = self._linter()
        violations = [(1, "open() with mode 'w' on journal path")]
        lines = ['open("journal.log", "w")  # noqa: journal-mutation']
        result = linter._filter_violations_by_noqa(violations, lines)
        assert len(result) == 1
        # Per review patch: bare noqa on real violation has its own message
        assert "real violation" in result[0][1].lower()

    @pytest.mark.unit
    def test_expand_targets_directory(self, tmp_path: Path) -> None:
        linter = self._linter()
        f1 = tmp_path / "a.py"
        f1.write_text("x = 1", encoding="utf-8")
        result = linter._expand_targets([str(tmp_path)])
        assert f1 in result

    @pytest.mark.unit
    def test_scan_file_unreadable_returns_empty(self, tmp_path: Path) -> None:
        linter = self._linter()
        missing = tmp_path / "nonexistent.py"
        result = linter._scan_file(missing)
        assert result == []

    @pytest.mark.unit
    def test_scan_file_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        linter = self._linter()
        bad = tmp_path / "bad.py"
        bad.write_text("def (:", encoding="utf-8")
        result = linter._scan_file(bad)
        assert result == []

    @pytest.mark.unit
    def test_is_exempt_self(self) -> None:
        linter = self._linter()
        assert linter._is_exempt(_SCRIPT)

    @pytest.mark.unit
    def test_is_exempt_writer_py(self) -> None:
        linter = self._linter()
        writer = _SCRIPT.parent.parent / "src" / "sdlc" / "journal" / "writer.py"
        assert linter._is_exempt(writer)

    @pytest.mark.unit
    def test_is_exempt_outside_repo_returns_false(self, tmp_path: Path) -> None:
        linter = self._linter()
        outside = tmp_path / "outside.py"
        outside.write_text("x = 1", encoding="utf-8")
        assert not linter._is_exempt(outside)

    @pytest.mark.unit
    def test_is_exempt_tests_dir_returns_true(self) -> None:
        linter = self._linter()
        tests_file = _SCRIPT.parent.parent / "tests" / "unit" / "test_something.py"
        assert linter._is_exempt(tests_file)

    @pytest.mark.unit
    def test_expand_targets_single_file(self, tmp_path: Path) -> None:
        linter = self._linter()
        f = tmp_path / "foo.py"
        f.write_text("x = 1", encoding="utf-8")
        result = linter._expand_targets([str(f)])
        assert f in result

    @pytest.mark.unit
    def test_check_open_too_few_args_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('open("journal.log")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_open_call(call) is None

    @pytest.mark.unit
    def test_check_open_non_journal_path_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('open("output.log", "w")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_open_call(call) is None

    @pytest.mark.unit
    def test_check_path_write_non_journal_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('Path("output.txt").write_text("x")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_path_write_call(call) is None

    @pytest.mark.unit
    def test_check_replace_non_os_module_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('shutil.replace("/tmp/x", "journal.log")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_replace_call(call) is None

    @pytest.mark.unit
    def test_check_replace_too_few_args_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('os.replace("journal.log")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_replace_call(call) is None

    @pytest.mark.unit
    def test_check_replace_non_journal_dst_no_violation(self) -> None:
        linter = self._linter()
        tree = ast.parse('os.replace("/tmp/x", "/tmp/output.txt")')
        call = tree.body[0].value  # type: ignore[union-attr]
        assert linter._check_replace_call(call) is None

    @pytest.mark.unit
    def test_visitor_function_call_not_attribute_no_violation(self) -> None:
        """Function calls (not method calls) inside a function don't trigger seek detector."""
        code = """\
            def fn():
                seek(0)
                write(b"x")
        """
        violations = self._visit(code)
        assert violations == []

    @pytest.mark.unit
    def test_visitor_async_function_seek_write(self) -> None:
        code = """\
            async def async_bad():
                f.seek(0)
                f.write(b"x")
        """
        violations = self._visit(code)
        assert len(violations) == 1
        assert "seek" in violations[0][1].lower()

    @pytest.mark.unit
    def test_filter_violations_no_noqa_keeps_violation(self) -> None:
        linter = self._linter()
        violations = [(1, "open() with mode 'w' on journal path")]
        lines = ['open("journal.log", "w")  # plain comment']
        result = linter._filter_violations_by_noqa(violations, lines)
        assert result == violations

    @pytest.mark.unit
    def test_find_bare_noqa_standalone_comment(self) -> None:
        linter = self._linter()
        lines = ["x = 1  # noqa: journal-mutation"]
        result = linter._find_bare_noqa(lines, existing=[])
        assert len(result) == 1
        # Distinct stray-noqa message vs violation-noqa message (review patch L)
        assert "stray" in result[0][1].lower()

    @pytest.mark.unit
    def test_find_bare_noqa_with_existing_lineno_skipped(self) -> None:
        linter = self._linter()
        lines = ['open("journal.log", "w")  # noqa: journal-mutation']
        existing = [(1, "some existing violation")]
        result = linter._find_bare_noqa(lines, existing=existing)
        assert result == []

    @pytest.mark.unit
    def test_scan_file_with_violations(self, tmp_path: Path) -> None:
        linter = self._linter()
        f = tmp_path / "bad.py"
        f.write_text('open("journal.log", "w")', encoding="utf-8")
        result = linter._scan_file(f)
        assert len(result) >= 1
        assert any("open()" in msg for _, msg in result)

    @pytest.mark.unit
    def test_main_with_violations_returns_1(self, tmp_path: Path) -> None:
        linter = self._linter()
        f = tmp_path / "bad.py"
        f.write_text('open("journal.log", "w")', encoding="utf-8")
        assert linter.main([str(f)]) == 1

    @pytest.mark.unit
    def test_main_clean_returns_0(self, tmp_path: Path) -> None:
        linter = self._linter()
        f = tmp_path / "clean.py"
        f.write_text('open("output.txt", "w")', encoding="utf-8")
        assert linter.main([str(f)]) == 0

    @pytest.mark.unit
    def test_main_exempt_file_skipped(self) -> None:
        """main() skips exempt files (tests/ dir) and returns 0 even with violations inside."""
        linter = self._linter()
        tests_file = _SCRIPT.parent.parent / "tests" / "unit" / "test_journal_mutation_validator.py"
        assert linter.main([str(tests_file)]) == 0

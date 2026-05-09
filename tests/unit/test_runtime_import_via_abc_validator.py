"""Unit tests for scripts/check_runtime_import_via_abc.py (AC4, Story 1.13).

Mirrors tests/unit/test_journal_mutation_validator.py (Story 1.11) and
tests/unit/test_state_write_validator.py (Story 1.10) patterns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_runtime_import_via_abc.py"
_FIXTURES = Path(__file__).parent.parent / "fixtures" / "lint_negative"
_REPO_ROOT = Path(__file__).parent.parent.parent
_ENGINE_DIR = _REPO_ROOT / "src" / "sdlc" / "engine"
_DISPATCHER_DIR = _REPO_ROOT / "src" / "sdlc" / "dispatcher"
_CLI_DIR = _REPO_ROOT / "src" / "sdlc" / "cli"


def _load_check_file() -> object:
    """Import check_file from the validator script for in-process AST testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_runtime_import_via_abc", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_check_file()
_check_file = _mod._check_file  # type: ignore[attr-defined]
_is_guarded = _mod._is_guarded  # type: ignore[attr-defined]
_is_permissive = _mod._is_permissive  # type: ignore[attr-defined]


def _write_fixture(tmp_path: Path, subdir: str, code: str) -> Path:
    """Write a Python file under a simulated guarded parent path."""
    parent = tmp_path / "src" / "sdlc" / subdir
    parent.mkdir(parents=True, exist_ok=True)
    f = parent / "test_module.py"
    f.write_text(code, encoding="utf-8")
    return f


@pytest.mark.unit
def test_validator_allows_canonical_import_in_engine(tmp_path: Path) -> None:
    """from sdlc.runtime import AIRuntime is allowed in engine/."""
    code = "from sdlc.runtime import AIRuntime\n"
    # Build a path that looks like engine/ but in tmp_path
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert violations == [], f"unexpected violations: {violations}"


@pytest.mark.unit
def test_validator_flags_mock_direct_import_in_engine(tmp_path: Path) -> None:
    """from sdlc.runtime.mock import MockAIRuntime is forbidden in engine/."""
    fixture = _FIXTURES / "engine_imports_runtime_mock.py.txt"
    code = fixture.read_text(encoding="utf-8")
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    line, msg = violations[0]
    assert line == 1
    assert "sdlc.runtime.mock" in msg


@pytest.mark.unit
def test_validator_flags_claude_direct_import_in_dispatcher(tmp_path: Path) -> None:
    """from sdlc.runtime.claude import ClaudeAIRuntime is forbidden in dispatcher/."""
    fixture = _FIXTURES / "dispatcher_imports_runtime_claude.py.txt"
    code = fixture.read_text(encoding="utf-8")
    dispatcher_path = tmp_path / "src" / "sdlc" / "dispatcher"
    dispatcher_path.mkdir(parents=True)
    f = dispatcher_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    line, msg = violations[0]
    assert line == 1
    assert "sdlc.runtime.claude" in msg


@pytest.mark.unit
def test_validator_flags_abc_direct_import_in_engine(tmp_path: Path) -> None:
    """from sdlc.runtime.abc import AIRuntime is forbidden — use re-export."""
    fixture = _FIXTURES / "engine_imports_runtime_abc.py.txt"
    code = fixture.read_text(encoding="utf-8")
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    _, msg = violations[0]
    assert "sdlc.runtime.abc" in msg


@pytest.mark.unit
def test_validator_ignores_non_engine_dispatcher_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files outside engine/ and dispatcher/ are not checked by this validator.

    Repoints _GUARDED_PARENTS to tmp_path-relative parents and verifies that:
    - a state/ file is NOT considered guarded (the rule only fires in engine/dispatcher);
    - an engine/ file under the same fake root IS considered guarded (sanity check that
      the harness works — guards previous bug where a vacuous tmp_path was compared
      against the real _REPO_ROOT).
    """
    fake_engine = tmp_path / "src" / "sdlc" / "engine"
    fake_dispatcher = tmp_path / "src" / "sdlc" / "dispatcher"
    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (fake_engine, fake_dispatcher))

    state_path = tmp_path / "src" / "sdlc" / "state"
    state_path.mkdir(parents=True)
    state_file = state_path / "test.py"
    state_file.write_text("from sdlc.runtime.mock import MockAIRuntime\n", encoding="utf-8")
    assert not _is_guarded(state_file), "state/ should NOT be guarded"

    fake_engine.mkdir(parents=True)
    engine_file = fake_engine / "test.py"
    engine_file.write_text("from sdlc.runtime.mock import MockAIRuntime\n", encoding="utf-8")
    assert _is_guarded(engine_file), (
        "engine/ under the same fake root SHOULD be guarded — proves the test harness "
        "actually exercises _GUARDED_PARENTS"
    )


@pytest.mark.unit
def test_validator_reports_line_numbers(tmp_path: Path) -> None:
    """Violation messages include the line number of the forbidden import."""
    code = "# comment\n\nfrom sdlc.runtime.mock import MockAIRuntime\n"
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    line, _ = violations[0]
    assert line == 3


@pytest.mark.unit
def test_is_guarded_returns_true_for_engine(tmp_path: Path) -> None:
    """_is_guarded correctly identifies engine/ files — using real repo path."""
    if _ENGINE_DIR.exists():
        # Pick any .py file in engine/ if it exists
        py_files = list(_ENGINE_DIR.rglob("*.py"))
        if py_files:
            assert _is_guarded(py_files[0])


@pytest.mark.unit
def test_is_permissive_returns_true_for_cli(tmp_path: Path) -> None:
    """_is_permissive correctly identifies cli/ files — using real repo path."""
    if _CLI_DIR.exists():
        py_files = list(_CLI_DIR.rglob("*.py"))
        if py_files:
            assert _is_permissive(py_files[0])


# ---------------------------------------------------------------------------
# _check_import_from line 64: non-runtime module falls through to return []
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_import_from_non_runtime_module_returns_empty(tmp_path: Path) -> None:
    """from sdlc.engine import X in a guarded file → _check_import_from returns []."""
    code = "from sdlc.engine import scanner\n"
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "probe.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert violations == []


# ---------------------------------------------------------------------------
# _check_import (lines 73-87): bare `import sdlc.runtime.<sub>` path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_file_flags_bare_import_syntax(tmp_path: Path) -> None:
    """`import sdlc.runtime.mock` triggers _check_import (ast.Import path)."""
    code = "import sdlc.runtime.mock\n"
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "bad.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    _, msg = violations[0]
    assert "sdlc.runtime.mock" in msg


@pytest.mark.unit
def test_check_file_allows_bare_import_sdlc_runtime(tmp_path: Path) -> None:
    """`import sdlc.runtime` is the allowed form — _check_import returns []."""
    code = "import sdlc.runtime\n"
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "ok.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert violations == []


@pytest.mark.unit
def test_check_import_reports_line_number_for_bare_import(tmp_path: Path) -> None:
    """_check_import violation includes the line number."""
    code = "# comment\n\nimport sdlc.runtime.claude\n"
    engine_path = tmp_path / "src" / "sdlc" / "engine"
    engine_path.mkdir(parents=True)
    f = engine_path / "test.py"
    f.write_text(code, encoding="utf-8")
    violations = _check_file(f)
    assert len(violations) == 1
    line, msg = violations[0]
    assert line == 3
    assert "sdlc.runtime.claude" in msg


# ---------------------------------------------------------------------------
# _check_file error branches: OSError and SyntaxError
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_file_returns_empty_on_missing_file(tmp_path: Path) -> None:
    """Non-existent path triggers OSError → _check_file skips with warning."""
    p = tmp_path / "nonexistent.py"
    violations = _check_file(p)
    assert violations == []


@pytest.mark.unit
def test_check_file_returns_empty_on_syntax_error(tmp_path: Path) -> None:
    """Files with syntax errors are skipped (SyntaxError branch)."""
    p = tmp_path / "bad_syntax.py"
    p.write_text("def broken(\n", encoding="utf-8")
    violations = _check_file(p)
    assert violations == []


# ---------------------------------------------------------------------------
# _expand_targets (lines 123-135)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expand_targets_with_directory_globs_py_files(tmp_path: Path) -> None:
    """Directory input expands to all *.py files recursively."""
    sub = tmp_path / "sub"
    sub.mkdir()
    f = sub / "module.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = _mod._expand_targets([str(tmp_path)])
    assert f in result


@pytest.mark.unit
def test_expand_targets_with_py_file(tmp_path: Path) -> None:
    """A .py file path is accepted directly."""
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = _mod._expand_targets([str(f)])
    assert f in result


@pytest.mark.unit
def test_expand_targets_accepts_py_txt_fixtures(tmp_path: Path) -> None:
    """*.py.txt lint fixture files are accepted."""
    f = tmp_path / "fixture.py.txt"
    f.write_text("from sdlc.runtime.mock import X\n", encoding="utf-8")
    result = _mod._expand_targets([str(f)])
    assert f in result


@pytest.mark.unit
def test_expand_targets_warns_and_skips_non_py(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-.py files produce a warning and are excluded from results."""
    f = tmp_path / "README.md"
    f.write_text("# doc\n", encoding="utf-8")
    result = _mod._expand_targets([str(f)])
    assert result == []
    assert "warning" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# _default_targets (lines 138-143)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_targets_returns_empty_when_guarded_dirs_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_default_targets returns [] when guarded parents do not exist on disk."""
    from pathlib import Path

    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (Path("/nonexistent/engine"),))
    result = _mod._default_targets()
    assert result == []


@pytest.mark.unit
def test_default_targets_returns_py_files_from_existing_guarded_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_default_targets globs *.py from existing guarded parents."""
    fake_engine = tmp_path / "engine"
    fake_engine.mkdir()
    f = fake_engine / "scanner.py"
    f.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (fake_engine,))
    result = _mod._default_targets()
    assert f in result


# ---------------------------------------------------------------------------
# main() (lines 146-164)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_main_returns_0_for_no_argv_no_guarded_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main([]) with no guarded parents → _default_targets yields nothing → exit 0."""
    from pathlib import Path

    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (Path("/nonexistent"),))
    assert _mod.main([]) == 0


@pytest.mark.unit
def test_main_returns_1_for_forbidden_import_in_guarded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() returns 1 when a guarded file has a forbidden runtime import."""
    engine_path = tmp_path / "engine"
    engine_path.mkdir()
    f = engine_path / "bad.py"
    f.write_text("from sdlc.runtime.mock import MockAIRuntime\n", encoding="utf-8")
    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (engine_path,))
    monkeypatch.setattr(_mod, "_PERMISSIVE_PARENTS", ())
    assert _mod.main([str(f)]) == 1


@pytest.mark.unit
def test_main_returns_0_for_allowed_import_in_guarded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() returns 0 when a guarded file only uses the canonical import."""
    engine_path = tmp_path / "engine"
    engine_path.mkdir()
    f = engine_path / "ok.py"
    f.write_text("from sdlc.runtime import AIRuntime\n", encoding="utf-8")
    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (engine_path,))
    monkeypatch.setattr(_mod, "_PERMISSIVE_PARENTS", ())
    assert _mod.main([str(f)]) == 0


@pytest.mark.unit
def test_main_skips_permissive_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Files under permissive parents are skipped even if they contain forbidden imports."""
    cli_path = tmp_path / "cli"
    cli_path.mkdir()
    f = cli_path / "tool.py"
    f.write_text("from sdlc.runtime.mock import MockAIRuntime\n", encoding="utf-8")
    engine_path = tmp_path / "engine"
    monkeypatch.setattr(_mod, "_GUARDED_PARENTS", (engine_path,))
    monkeypatch.setattr(_mod, "_PERMISSIVE_PARENTS", (cli_path,))
    assert _mod.main([str(f)]) == 0

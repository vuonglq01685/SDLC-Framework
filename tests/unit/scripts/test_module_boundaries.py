"""Unit tests for scripts/check_module_boundaries.py — migrations module entries (AC7.6)."""

from __future__ import annotations

import ast

import pytest

import check_module_boundaries as guard

pytestmark = pytest.mark.unit


def _imports_from_code(code: str) -> list[guard.Import]:
    tree = ast.parse(code)
    return guard._extract_sdlc_imports(tree, src_module="migrations")


# ---------------------------------------------------------------------------
# MODULE_DEPS registry — migrations entry
# ---------------------------------------------------------------------------


def test_migrations_entry_exists_in_module_deps() -> None:
    assert "migrations" in guard.MODULE_DEPS


def test_migrations_depends_on_errors() -> None:
    assert "errors" in guard.MODULE_DEPS["migrations"].depends_on


def test_migrations_depends_on_state() -> None:
    assert "state" in guard.MODULE_DEPS["migrations"].depends_on


def test_migrations_forbidden_from_engine() -> None:
    assert "engine" in guard.MODULE_DEPS["migrations"].forbidden_from


def test_migrations_forbidden_from_dispatcher() -> None:
    assert "dispatcher" in guard.MODULE_DEPS["migrations"].forbidden_from


def test_migrations_forbidden_from_runtime() -> None:
    assert "runtime" in guard.MODULE_DEPS["migrations"].forbidden_from


def test_migrations_forbidden_from_cli() -> None:
    assert "cli" in guard.MODULE_DEPS["migrations"].forbidden_from


def test_cli_depends_on_migrations() -> None:
    assert "migrations" in guard.MODULE_DEPS["cli"].depends_on


# ---------------------------------------------------------------------------
# check_imports behaviour for migrations source module
# ---------------------------------------------------------------------------


def test_migrations_importing_errors_is_allowed() -> None:
    imports = _imports_from_code("from sdlc.errors import SchemaError\n")
    violations = guard.check_imports("migrations", imports)
    assert violations == []


def test_migrations_importing_state_reader_is_allowed() -> None:
    imports = _imports_from_code("from sdlc.state.reader import CURRENT_SCHEMA_VERSION\n")
    violations = guard.check_imports("migrations", imports)
    assert violations == []


def test_migrations_importing_cli_is_forbidden() -> None:
    imports = _imports_from_code("from sdlc.cli.output import emit_error\n")
    violations = guard.check_imports("migrations", imports)
    assert len(violations) > 0
    assert any("cli" in v for v in violations)


def test_migrations_importing_engine_is_forbidden() -> None:
    imports = _imports_from_code("from sdlc.engine.scanner import Scanner\n")
    violations = guard.check_imports("migrations", imports)
    assert len(violations) > 0
    assert any("engine" in v for v in violations)


def test_migrations_importing_runtime_is_forbidden() -> None:
    imports = _imports_from_code("from sdlc.runtime.abc import RuntimeABC\n")
    violations = guard.check_imports("migrations", imports)
    assert len(violations) > 0
    assert any("runtime" in v for v in violations)

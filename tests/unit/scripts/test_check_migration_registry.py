"""Unit tests for scripts/check_migration_registry.py (AC7.7)."""

from __future__ import annotations

import sys
import types

import pytest

import check_migration_registry as registry_script

pytestmark = pytest.mark.unit


def _inject_module(monkeypatch: pytest.MonkeyPatch, version: int, code: str) -> None:
    """Register a synthetic sdlc.migrations.vN module in sys.modules."""
    mod_name = f"sdlc.migrations.v{version}"
    mod = types.ModuleType(mod_name)
    exec(compile(code, f"<v{version}>", "exec"), mod.__dict__)
    monkeypatch.setitem(sys.modules, mod_name, mod)


# ---------------------------------------------------------------------------
# main() with v1 build (no migrations expected)
# ---------------------------------------------------------------------------


def test_main_returns_0_for_v1_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 1)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [])
    assert registry_script.main() == 0


def test_main_prints_ok_for_v1_build(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 1)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [])
    registry_script.main()
    out = capsys.readouterr().out
    assert "migration registry OK" in out


# ---------------------------------------------------------------------------
# main() with v2 build — valid v2 script present
# ---------------------------------------------------------------------------


def test_main_returns_0_when_v2_script_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _inject_module(monkeypatch, 2, "def migrate(state): return state\n")

    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2])

    from sdlc.migrations import load_migration

    monkeypatch.setattr("sdlc.migrations.load_migration", load_migration)
    assert registry_script.main() == 0


# ---------------------------------------------------------------------------
# main() — missing script for expected version
# ---------------------------------------------------------------------------


def test_main_returns_1_when_script_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [])

    def _failing_load(n: int) -> object:
        from sdlc.errors import SchemaError

        raise SchemaError(
            f"v{n} not found",
            details={"code": "ERR_MIGRATION_NOT_FOUND", "available": []},
        )

    monkeypatch.setattr("sdlc.migrations.load_migration", _failing_load)
    assert registry_script.main() == 1


def test_main_prints_error_when_script_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [])
    monkeypatch.setattr("sdlc.migrations.load_migration", lambda n: None)
    registry_script.main()
    err = capsys.readouterr().err
    assert "missing migration script" in err


# ---------------------------------------------------------------------------
# main() — invalid script (bad signature)
# ---------------------------------------------------------------------------


def test_main_returns_1_when_script_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2])

    def _invalid_load(n: int) -> object:
        from sdlc.errors import SchemaError

        raise SchemaError(
            f"v{n} invalid",
            details={"code": "ERR_MIGRATION_INVALID", "reason": "wrong-signature"},
        )

    monkeypatch.setattr("sdlc.migrations.load_migration", _invalid_load)
    assert registry_script.main() == 1


# ---------------------------------------------------------------------------
# main() — extra script beyond CURRENT_SCHEMA_VERSION (warning only)
# ---------------------------------------------------------------------------


def test_main_returns_0_with_extra_script_as_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _inject_module(monkeypatch, 2, "def migrate(state): return state\n")

    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 1)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2])

    from sdlc.migrations import load_migration

    monkeypatch.setattr("sdlc.migrations.load_migration", load_migration)
    assert registry_script.main() == 0


def test_main_prints_warning_for_extra_script(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _inject_module(monkeypatch, 2, "def migrate(state): return state\n")

    monkeypatch.setattr("sdlc.state.reader.CURRENT_SCHEMA_VERSION", 1)
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2])

    from sdlc.migrations import load_migration

    monkeypatch.setattr("sdlc.migrations.load_migration", load_migration)
    registry_script.main()
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert "v2" in err

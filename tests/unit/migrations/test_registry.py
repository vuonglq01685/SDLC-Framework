"""Unit tests for sdlc.migrations registry (AC7.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_discover_migrations_empty_returns_empty_list() -> None:
    from sdlc.migrations import discover_migrations

    assert discover_migrations() == []


def test_discover_migrations_finds_synthetic_v2_via_monkeypatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    v2 = tmp_path / "v2.py"
    v2.write_text("def migrate(state): return state\n")

    fake_pkg = types.ModuleType("sdlc.migrations")
    fake_pkg.__path__ = [str(tmp_path)]  # type: ignore[assignment]
    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])

    from sdlc.migrations import discover_migrations

    assert discover_migrations() == [2]


def test_discover_migrations_ignores_non_v_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("_helpers.py", "__init__.py", "vfoo.py", "v0.py", "v01.py"):
        (tmp_path / name).write_text("")

    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])

    from sdlc.migrations import discover_migrations

    assert discover_migrations() == []


def test_discover_migrations_sorts_ascending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("v3.py", "v10.py", "v2.py"):
        (tmp_path / name).write_text("def migrate(state): return state\n")

    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])

    from sdlc.migrations import discover_migrations

    assert discover_migrations() == [2, 3, 10]


def test_load_migration_returns_callable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "v2.py").write_text("def migrate(state): return state\n")
    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])
    monkeypatch.syspath_prepend(str(tmp_path.parent))

    # Patch importlib to resolve v2 from tmp_path
    import sys

    module_name = "sdlc.migrations.v2"

    import types

    mod = types.ModuleType(module_name)
    exec(
        compile((tmp_path / "v2.py").read_text(), str(tmp_path / "v2.py"), "exec"),
        mod.__dict__,
    )
    sys.modules[module_name] = mod
    monkeypatch.setitem(sys.modules, module_name, mod)

    from sdlc.migrations import load_migration

    fn = load_migration(2)
    assert callable(fn)

    # cleanup
    sys.modules.pop(module_name, None)


def test_load_migration_raises_when_missing() -> None:
    from sdlc.errors import SchemaError
    from sdlc.migrations import discover_migrations, load_migration

    with pytest.raises(SchemaError) as exc_info:
        load_migration(99)
    assert "ERR_MIGRATION_NOT_FOUND" in str(exc_info.value.details.get("code", ""))
    assert exc_info.value.details.get("available") == discover_migrations()


def test_load_migration_raises_when_no_migrate_callable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    (tmp_path / "v2.py").write_text("x = 1\n")
    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])

    module_name = "sdlc.migrations.v2"
    mod = types.ModuleType(module_name)
    exec(
        compile((tmp_path / "v2.py").read_text(), str(tmp_path / "v2.py"), "exec"),
        mod.__dict__,
    )
    monkeypatch.setitem(sys.modules, module_name, mod)

    from sdlc.errors import SchemaError
    from sdlc.migrations import load_migration

    with pytest.raises(SchemaError) as exc_info:
        load_migration(2)
    assert exc_info.value.details.get("code") == "ERR_MIGRATION_INVALID"


def test_load_migration_raises_when_signature_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    (tmp_path / "v2.py").write_text("def migrate(): return {}\n")
    monkeypatch.setattr("sdlc.migrations.__path__", [str(tmp_path)])

    module_name = "sdlc.migrations.v2"
    mod = types.ModuleType(module_name)
    exec(
        compile((tmp_path / "v2.py").read_text(), str(tmp_path / "v2.py"), "exec"),
        mod.__dict__,
    )
    monkeypatch.setitem(sys.modules, module_name, mod)

    from sdlc.errors import SchemaError
    from sdlc.migrations import load_migration

    with pytest.raises(SchemaError) as exc_info:
        load_migration(2)
    assert exc_info.value.details.get("code") == "ERR_MIGRATION_INVALID"
    assert exc_info.value.details.get("reason") == "wrong-signature"


def test_current_schema_version_reexport() -> None:
    from sdlc.migrations import CURRENT_SCHEMA_VERSION

    assert CURRENT_SCHEMA_VERSION == 1

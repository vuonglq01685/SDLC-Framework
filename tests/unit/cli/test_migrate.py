"""Unit tests for sdlc.cli.migrate (AC7.4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import typer

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = False
    ctx.obj["json"] = json_mode
    return ctx


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# _resolve_paths
# ---------------------------------------------------------------------------


def test_resolve_paths_returns_correct_components(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _resolve_paths

    state_path, backup_dir, backup_path = _resolve_paths(tmp_path, 2)
    assert state_path == tmp_path / ".claude/state/state.json"
    assert backup_dir == tmp_path / ".claude/state/backups"
    assert backup_path == backup_dir / "state.json.pre-migrate-v2.json"


def test_resolve_paths_version_in_filename(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _resolve_paths

    _, _, backup_path = _resolve_paths(tmp_path, 7)
    assert "v7" in backup_path.name


# ---------------------------------------------------------------------------
# _check_state_initialized_or_refuse
# ---------------------------------------------------------------------------


def test_check_state_initialized_or_refuse_exits_when_missing(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _check_state_initialized_or_refuse

    ctx = _make_ctx()
    missing = tmp_path / "no_state.json"
    with pytest.raises(typer.Exit):
        _check_state_initialized_or_refuse(ctx, missing, tmp_path)


def test_check_state_initialized_or_refuse_passes_when_exists(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _check_state_initialized_or_refuse

    ctx = _make_ctx()
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    _check_state_initialized_or_refuse(ctx, state, tmp_path)  # no raise


# ---------------------------------------------------------------------------
# _create_backup
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_create_backup_copies_file(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _create_backup

    source = tmp_path / "state.json"
    source.write_bytes(b'{"schema_version":1}')
    backup = tmp_path / "backups" / "state.json.pre-migrate-v2.json"
    _create_backup(source, backup)
    assert backup.exists()
    assert backup.read_bytes() == source.read_bytes()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_create_backup_raises_state_error_if_backup_exists(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _create_backup
    from sdlc.errors import StateError

    source = tmp_path / "state.json"
    source.write_bytes(b'{"schema_version":1}')
    backup = tmp_path / "backups" / "state.json.pre-migrate-v2.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(b"existing-backup")

    with pytest.raises(StateError) as exc_info:
        _create_backup(source, backup)
    assert exc_info.value.details.get("reason") == "backup_exists"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_create_backup_raises_state_error_on_integrity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from sdlc.errors import StateError

    original_copy2 = shutil.copy2

    def _corrupt_copy(src: Any, dst: Any, **kwargs: Any) -> Any:
        result = original_copy2(src, dst, **kwargs)
        Path(str(dst)).write_bytes(b"corrupted")
        return result

    monkeypatch.setattr(shutil, "copy2", _corrupt_copy)

    from sdlc.cli.migrate import _create_backup

    source = tmp_path / "state.json"
    source.write_bytes(b'{"schema_version":1}')
    backup = tmp_path / "backups" / "state.json.pre-migrate-v2.json"
    with pytest.raises(StateError):
        _create_backup(source, backup)


# ---------------------------------------------------------------------------
# _validate_migration_result
# ---------------------------------------------------------------------------


def test_validate_migration_result_accepts_valid_dict(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _validate_migration_result

    result = {"schema_version": 2, "epics": {}}
    out = _validate_migration_result(result, 2, tmp_path / "state.json")
    assert out is result


def test_validate_migration_result_rejects_non_dict(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _validate_migration_result
    from sdlc.errors import SchemaError

    with pytest.raises(SchemaError) as exc_info:
        _validate_migration_result("not-a-dict", 2, tmp_path / "state.json")
    assert exc_info.value.details.get("code") == "ERR_MIGRATION_INVALID"


def test_validate_migration_result_rejects_wrong_schema_version(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _validate_migration_result
    from sdlc.errors import SchemaError

    with pytest.raises(SchemaError) as exc_info:
        _validate_migration_result({"schema_version": 3}, 2, tmp_path / "state.json")
    assert exc_info.value.details.get("code") == "ERR_MIGRATION_INVALID"


def test_validate_migration_result_rejects_missing_schema_version(tmp_path: Path) -> None:
    from sdlc.cli.migrate import _validate_migration_result
    from sdlc.errors import SchemaError

    with pytest.raises(SchemaError) as exc_info:
        _validate_migration_result({"foo": "bar"}, 2, tmp_path / "state.json")
    assert exc_info.value.details.get("code") == "ERR_MIGRATION_INVALID"


# ---------------------------------------------------------------------------
# _emit_success / _emit_no_op
# ---------------------------------------------------------------------------


def test_emit_no_op_plain_text(capsys: pytest.CaptureFixture[str]) -> None:
    from sdlc.cli.migrate import _emit_no_op

    _emit_no_op(_make_ctx(), 2)
    out = capsys.readouterr().out
    assert "already at schema_version=2" in out


def test_emit_no_op_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    from sdlc.cli.migrate import _emit_no_op

    _emit_no_op(_make_ctx(json_mode=True), 2)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["result"] == "no-op"
    assert data["schema_version"] == 2


def test_emit_success_plain_text(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from sdlc.cli.migrate import _emit_success

    backup = tmp_path / "backup.json"
    _emit_success(_make_ctx(), 1, 2, backup)
    out = capsys.readouterr().out
    assert "v1" in out and "v2" in out


def test_emit_success_json_mode(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from sdlc.cli.migrate import _emit_success

    backup = tmp_path / "backup.json"
    _emit_success(_make_ctx(json_mode=True), 1, 2, backup)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["result"] == "success"
    assert data["previous_schema_version"] == 1
    assert data["new_schema_version"] == 2


# ---------------------------------------------------------------------------
# run_migrate integration tests
#
# Patch targets for deferred imports (Architecture §488):
# run_migrate uses `from X import Y` inside the function body. On each call,
# Python re-executes the import statement but sdlc.migrations/sdlc.cli._paths
# are already cached in sys.modules, so the attribute is read from the cached
# module object. Patching the attribute on the SOURCE module (e.g.
# "sdlc.cli._paths.get_repo_root_or_cwd") IS seen by the deferred import.
# Never patch "sdlc.cli.migrate.<name>" — those local bindings don't exist
# at migrate module level.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_no_op_when_already_at_target(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    state_file = tmp_path / ".claude" / "state" / "state.json"
    _write_state(state_file, {"schema_version": 2, "epics": {}})

    ctx = _make_ctx()

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.migrations.discover_migrations", return_value=[2]),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_migrate(ctx, 2)
    assert exc_info.value.exit_code == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_succeeds_v1_to_v2(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    state_file = tmp_path / ".claude" / "state" / "state.json"
    _write_state(state_file, {"schema_version": 1, "epics": {}})

    ctx = _make_ctx()

    def _migrate(state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "schema_version": 2}

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.migrations.discover_migrations", return_value=[2]),
        patch("sdlc.migrations.load_migration", return_value=_migrate),
        patch("sdlc.state.atomic.write_state_raw_atomic_sync") as mock_write,
    ):
        run_migrate(ctx, 2)

    mock_write.assert_called_once()
    written_payload = mock_write.call_args[0][0]
    assert written_payload["schema_version"] == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_exits_if_state_missing(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    ctx = _make_ctx()

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        pytest.raises(typer.Exit),
    ):
        run_migrate(ctx, 2)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_exits_on_downgrade(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    state_file = tmp_path / ".claude" / "state" / "state.json"
    _write_state(state_file, {"schema_version": 3, "epics": {}})

    ctx = _make_ctx()

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.migrations.discover_migrations", return_value=[2, 3]),
        pytest.raises(typer.Exit),
    ):
        run_migrate(ctx, 2)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_exits_if_migration_not_found(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    state_file = tmp_path / ".claude" / "state" / "state.json"
    _write_state(state_file, {"schema_version": 1, "epics": {}})

    ctx = _make_ctx()

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.migrations.discover_migrations", return_value=[]),
        pytest.raises(typer.Exit),
    ):
        run_migrate(ctx, 2)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only atomic write")
def test_run_migrate_exits_if_migrate_fn_raises(tmp_path: Path) -> None:
    from sdlc.cli.migrate import run_migrate

    state_file = tmp_path / ".claude" / "state" / "state.json"
    _write_state(state_file, {"schema_version": 1, "epics": {}})

    ctx = _make_ctx()

    def _bad_migrate(state: dict[str, Any]) -> None:
        raise RuntimeError("something went wrong")

    with (
        patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
        patch("sdlc.migrations.discover_migrations", return_value=[2]),
        patch("sdlc.migrations.load_migration", return_value=_bad_migrate),
        pytest.raises(typer.Exit),
    ):
        run_migrate(ctx, 2)

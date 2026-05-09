"""sdlc migrate-vN orchestrator (FR49, NFR-DR-2, Architecture §810, §1175).

Loads migrations/v<N>.py via sdlc.migrations.load_migration; backs up state.json
to .claude/state/backups/state.json.pre-migrate-v<N>.json; runs migrate(); writes
the new state via the atomic write protocol. Idempotent: re-running on already-v<N>
state is a logged no-op (exit 0).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Final

import typer

from sdlc.cli.output import echo, emit_error, emit_json

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_BACKUP_DIR_REL: Final[str] = ".claude/state/backups"
_BACKUP_FILENAME_FORMAT: Final[str] = "state.json.pre-migrate-v{version}.json"
_STATE_REASON_MAP: Final[dict[str, str]] = {
    "json": "ERR_STATE_MALFORMED",
    "not_object": "ERR_STATE_MALFORMED",
    "io": "ERR_INFRASTRUCTURE",
}


def _resolve_paths(repo_root: Path, target_version: int) -> tuple[Path, Path, Path]:
    state_path = repo_root / _STATE_PATH_REL
    backup_dir = repo_root / _BACKUP_DIR_REL
    backup_path = backup_dir / _BACKUP_FILENAME_FORMAT.format(version=target_version)
    return state_path, backup_dir, backup_path


def _check_state_initialized_or_refuse(
    ctx: typer.Context, state_path: Path, repo_root: Path
) -> None:
    if not state_path.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"sdlc: project not initialized at {repo_root}; run `sdlc init` first",
            ctx=ctx,
            details={"path": str(state_path)},
        )


def _create_backup(state_path: Path, backup_path: Path) -> None:
    from sdlc.errors import StateError

    if backup_path.exists():
        raise StateError(
            f"backup already exists at {backup_path}; remove it manually to re-run migration",
            details={"path": str(backup_path), "reason": "backup_exists"},
        )
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(state_path, backup_path)
    except OSError as e:
        raise StateError(
            f"backup failed at {backup_path}: {e}",
            details={"path": str(backup_path), "errno": e.errno, "reason": "backup_copy"},
        ) from e
    # Integrity check — backup must be byte-identical to source.
    if backup_path.read_bytes() != state_path.read_bytes():
        raise StateError(
            "backup integrity check failed: backup bytes differ from source",
            details={"backup": str(backup_path), "source": str(state_path)},
        )


def _validate_migration_result(
    result: object, target_version: int, state_path: Path
) -> dict[str, Any]:
    from sdlc.errors import SchemaError

    if not isinstance(result, dict):
        raise SchemaError(
            f"migrations/v{target_version}.py:migrate returned an invalid result (not a dict)",
            details={
                "code": "ERR_MIGRATION_INVALID",
                "version": target_version,
                "path": str(state_path),
            },
        )
    if result.get("schema_version") != target_version:
        raise SchemaError(
            f"migrations/v{target_version}.py:migrate returned an invalid result"
            f" (schema_version != {target_version})",
            details={
                "code": "ERR_MIGRATION_INVALID",
                "version": target_version,
                "returned_schema_version": result.get("schema_version"),
            },
        )
    return result


def _emit_success(
    ctx: typer.Context,
    prev_version: int,
    new_version: int,
    backup_path: Path,
) -> None:
    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            f"migrate-v{new_version}",
            {
                "result": "success",
                "previous_schema_version": prev_version,
                "new_schema_version": new_version,
                "backup_path": str(backup_path),
            },
            ctx=ctx,
        )
    else:
        echo(
            f"migrated state.json: v{prev_version} → v{new_version}; backup at {backup_path}",
            ctx=ctx,
        )


def _emit_no_op(ctx: typer.Context, version: int) -> None:
    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            f"migrate-v{version}",
            {
                "result": "no-op",
                "schema_version": version,
                "reason": "already_at_target",
            },
            ctx=ctx,
        )
    else:
        echo(f"state.json is already at schema_version={version}; no migration needed", ctx=ctx)


def run_migrate(ctx: typer.Context, target_version: int) -> None:  # noqa: C901
    """Orchestrate the sdlc migrate-vN command (13-step flow, AC3.3)."""
    from sdlc.cli._paths import get_repo_root_or_cwd
    from sdlc.errors import SchemaError, StateError
    from sdlc.migrations import discover_migrations, load_migration
    from sdlc.state import read_state_raw
    from sdlc.state.atomic import write_state_raw_atomic_sync

    # Step 1 — repo root + path resolution.
    repo_root = get_repo_root_or_cwd()
    state_path, _backup_dir, backup_path = _resolve_paths(repo_root, target_version)

    # Step 2 — pre-flight: state.json must exist.
    _check_state_initialized_or_refuse(ctx, state_path, repo_root)

    # Step 3 — read raw state.
    try:
        state_dict = read_state_raw(state_path)
    except StateError as e:
        reason = e.details.get("reason", "")
        code = _STATE_REASON_MAP.get(str(reason), "ERR_STATE_MALFORMED")
        emit_error(code, e.message, ctx=ctx, details=e.details)

    # TOCTOU guard: state.json could be deleted between step 2's existence check and this read.
    if state_dict is None:
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"sdlc: project not initialized at {repo_root}; run `sdlc init` first",
            ctx=ctx,
            details={"path": str(state_path)},
        )

    # Step 4 — validate target_version.
    available = discover_migrations()
    if target_version not in available:
        emit_error(
            "ERR_MIGRATION_NOT_FOUND",
            f"no migration script for v{target_version}; available: {available}",
            ctx=ctx,
            details={"requested": target_version, "available": available},
        )

    # Step 5 — idempotency check.
    state_schema_version = state_dict.get("schema_version")
    if state_schema_version == target_version:
        _emit_no_op(ctx, target_version)
        raise typer.Exit(0)

    # Step 6 — version sanity guard.
    if state_schema_version is None or not isinstance(state_schema_version, int):
        emit_error(
            "ERR_STATE_MALFORMED",
            "state.json missing or non-integer schema_version",
            ctx=ctx,
            details={"path": str(state_path), "value": repr(state_schema_version)},
        )

    # Step 7 — version-direction guard (no downgrade in v1).
    # state_schema_version is int: step 6 calls emit_error (NoReturn) for any non-int value.
    if state_schema_version > target_version:
        emit_error(
            "ERR_MIGRATION_DOWNGRADE",
            f"state.json is at v{state_schema_version}; cannot migrate down"
            f" to v{target_version} (downgrades not supported in v1)",
            ctx=ctx,
            details={
                "state_version": state_schema_version,
                "target_version": target_version,
            },
        )

    # Step 8 — backup.
    try:
        _create_backup(state_path, backup_path)
    except StateError as e:
        emit_error("ERR_INFRASTRUCTURE", e.message, ctx=ctx, details=e.details)

    # Step 9 — load migration.
    try:
        migrate_fn = load_migration(target_version)
    except SchemaError as e:
        code = str(e.details.get("code", "ERR_MIGRATION_INVALID"))
        emit_error(code, e.message, ctx=ctx, details=e.details)  # NoReturn

    # Step 10 — run migration (sandboxed). emit_error is NoReturn; new_state_dict is bound after.
    try:
        new_state_dict = migrate_fn(state_dict)
    except Exception as e:
        emit_error(
            "ERR_MIGRATION_FAILED",
            f"migrations/v{target_version}.py:migrate raised: {type(e).__name__}: {e}",
            ctx=ctx,
            details={
                "version": target_version,
                "exception_type": type(e).__name__,
                "exception_repr": repr(e),
            },
        )

    # Step 11 — validate result.
    try:
        validated_dict = _validate_migration_result(new_state_dict, target_version, state_path)
    except SchemaError as e:
        emit_error("ERR_MIGRATION_INVALID", e.message, ctx=ctx, details=e.details)  # NoReturn

    # Step 12 — atomic write.
    try:
        write_state_raw_atomic_sync(validated_dict, state_path)
    except StateError as e:
        emit_error("ERR_STATE_WRITE_FAILED", e.message, ctx=ctx, details=e.details)

    # Step 13 — success output.
    _emit_success(ctx, state_schema_version, target_version, backup_path)

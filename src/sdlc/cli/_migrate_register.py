"""Dynamic migration command registration for the Typer app (Story 1.19)."""

from __future__ import annotations

import typer


def register_migrate_commands(app: typer.Typer) -> None:
    """Register one Typer command per discovered migration script.

    Called at module import — fast (one filesystem listing of the migrations
    package). For v1 with no migration scripts, this is a no-op.
    """
    from sdlc.migrations import discover_migrations  # deferred to function; called once

    for n in discover_migrations():

        def _make_command(version: int) -> typer.models.CommandFunctionType:  # type: ignore[type-var, misc]
            def _migrate_command(ctx: typer.Context) -> None:
                from sdlc.cli.migrate import run_migrate  # deferred per Architecture §488

                run_migrate(ctx=ctx, target_version=version)

            _migrate_command.__doc__ = f"Run schema migration to v{version} (FR49)."
            return _migrate_command  # type: ignore[return-value]

        app.command(name=f"migrate-v{n}")(_make_command(n))

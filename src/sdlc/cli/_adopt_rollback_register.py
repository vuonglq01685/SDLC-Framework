"""Registration for the `sdlc adopt-rollback` command (Story 3.5).

Mirrors ``_migrate_register`` to keep ``cli/main.py`` under the NFR-MAINT-3 LOC cap:
only the Typer command shell lives here; the rollback orchestration
(``run_adopt_rollback``) and error envelope are deferred into the command body
per Architecture §488 so the cold-start import set stays minimal.
"""

from __future__ import annotations

import typer


def register_adopt_rollback_command(app: typer.Typer) -> None:
    """Register the flat ``adopt-rollback`` command on the root app.

    Called at module import — only defines the command; the heavy orchestration
    imports run lazily inside the body (Architecture §488).
    """

    @app.command(name="adopt-rollback")
    def adopt_rollback_command(
        ctx: typer.Context,
        rollback_all: bool = typer.Option(False, "--all", help="Roll back every adopted symlink."),
        target: str | None = typer.Option(
            None,
            "--target",
            help="Repo-relative manifest target to roll back.",
        ),
        force: bool = typer.Option(
            False,
            "--force",
            help="Invalidate orphaned APPROVED signoffs and proceed with rollback.",
        ),
    ) -> None:
        """Remove adopted symlinks listed in adopted-symlinks.json (Story 3.5)."""
        from sdlc.cli.adopt_rollback import run_adopt_rollback  # deferred per Architecture §488
        from sdlc.cli.output import emit_error  # deferred per Architecture §488

        if rollback_all == (target is not None):
            emit_error("ERR_USER_INPUT", "specify exactly one of --all or --target", ctx=ctx)
        run_adopt_rollback(ctx=ctx, rollback_all=rollback_all, target=target, force=force)

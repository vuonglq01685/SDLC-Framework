"""Registration for `sdlc unsign` (Story 4.12)."""

from __future__ import annotations

import typer


def register_unsign_command(app: typer.Typer) -> None:
    @app.command(name="unsign")
    def unsign_command(
        ctx: typer.Context,
        mad_only: bool = typer.Option(
            False,
            "--mad-only",
            help="Remove only mad-mode signoffs (FR23).",
        ),
        include_clarifications: bool = typer.Option(
            False,
            "--include-clarifications",
            help="Also revert mad-resolved clarifications.",
        ),
    ) -> None:
        from sdlc.cli.unsign import run_unsign  # deferred per Architecture §488

        run_unsign(ctx=ctx, mad_only=mad_only, include_clarifications=include_clarifications)

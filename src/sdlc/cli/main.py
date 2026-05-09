"""Typer application entry — registers all `sdlc <subcommand>` handlers.

Per Architecture §488, command-body imports are deferred to keep the
cold-start budget under 200 ms; only the Typer machinery is imported at
module level.
"""

from __future__ import annotations

import typer

from sdlc.cli.version import get_version

__all__ = ("app",)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"sdlc {get_version()}")
        raise typer.Exit(code=0)


app = typer.Typer(
    name="sdlc",
    help="Deterministic, auditable, multi-agent SDLC orchestration framework.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the installed version and exit.",
    ),
) -> None:
    """SDLC framework CLI."""


@app.command(name="init")
def init_command() -> None:
    """Initialize the SDLC framework in the current git repository."""
    from sdlc.cli.init import run_init  # deferred per Architecture §488

    run_init()

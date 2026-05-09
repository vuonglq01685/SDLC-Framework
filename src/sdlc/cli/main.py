"""Typer application entry — registers all `sdlc <subcommand>` handlers.

Per Architecture §488, command-body imports are deferred to keep the
cold-start budget under 200 ms; only the Typer machinery is imported at
module level.
"""

from __future__ import annotations

import json
import os
import sys

import typer

from sdlc.cli.version import get_version

__all__ = ("app",)


def _version_callback(value: bool) -> None:
    if value:
        if "--json" in sys.argv:
            payload = json.dumps(
                {"command": "version", "version": get_version()},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            typer.echo(payload)
        else:
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
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the installed version and exit.",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        is_eager=True,
        help="Disable ANSI color in CLI output (NO_COLOR env var also honored).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        is_eager=True,
        help="Emit machine-readable JSON instead of human-readable output.",
    ),
) -> None:
    """SDLC framework CLI."""
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color or os.environ.get("NO_COLOR", "") != ""
    ctx.obj["json"] = json_output


@app.command(name="init")
def init_command(
    ctx: typer.Context,
    adopt: bool = typer.Option(False, "--adopt", help="Adopt an existing project.", hidden=True),
) -> None:
    """Initialize the SDLC framework in the current git repository."""
    if adopt:
        from sdlc.cli.output import emit_error

        emit_error(
            "ERR_USER_INPUT",
            "sdlc init --adopt is not implemented in v1.16 (Story 3.1+).",
            ctx=ctx,
        )
    from sdlc.cli.init import run_init  # deferred per Architecture §488

    run_init(ctx=ctx)


@app.command(name="scan")
def scan_command(ctx: typer.Context) -> None:
    """Refresh state.json from the artifact tree (FR3)."""
    from sdlc.cli.scan import run_scan  # deferred per Architecture §488

    run_scan(ctx=ctx)


@app.command(name="status")
def status_command(ctx: typer.Context) -> None:
    """Print the resume card with suggested next-action (FR44)."""
    from sdlc.cli.status import run_status  # deferred

    run_status(ctx=ctx)

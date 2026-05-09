"""Typer application entry — registers all `sdlc <subcommand>` handlers.

Per Architecture §488, command-body imports are deferred to keep the
cold-start budget under 200 ms; only the Typer machinery is imported at
module level.
"""

from __future__ import annotations

import os
import sys

import typer

from sdlc.cli.version import get_version

__all__ = ("app",)


def _version_callback(value: bool) -> None:
    if value:
        if "--json" in sys.argv:
            from sdlc.cli.output import canonical_dumps  # deferred per Architecture §488

            typer.echo(canonical_dumps({"command": "version", "version": get_version()}))
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
            "sdlc init --adopt is not implemented yet (Story 3.1+).",
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


@app.command(name="trace")
def trace_command(
    ctx: typer.Context,
    task_id: str = typer.Argument(..., help="Task identifier (EPIC-...-S<NN>-...-T<NN>-...)."),
) -> None:
    """Reconstruct chronological history of a task (FR33)."""
    from sdlc.cli.trace import run_trace  # deferred per Architecture §488

    run_trace(ctx=ctx, task_id=task_id)


@app.command(name="replay")
def replay_command(
    ctx: typer.Context,
    line_spec: str = typer.Argument(..., help="Line number or range (e.g. '42' or '42-50')."),
) -> None:
    """Pretty-print parsed journal entries by line (FR34)."""
    from sdlc.cli.replay import run_replay  # deferred

    run_replay(ctx=ctx, line_spec=line_spec)


@app.command(name="logs")
def logs_command(
    ctx: typer.Context,
    filter_task: str | None = typer.Option(
        None, "--filter-task", help="Restrict to entries matching this task-id."
    ),
    filter_agent: str | None = typer.Option(
        None, "--filter-agent", help="Restrict to entries from this agent."
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Tail-follow streams; exit on Ctrl-C."
    ),
) -> None:
    """Tail journal + agent_runs.jsonl with filters (FR45, NFR-OBS-6)."""
    from sdlc.cli.logs import run_logs  # deferred

    run_logs(ctx=ctx, filter_task=filter_task, filter_agent=filter_agent, follow=follow)

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


@app.command(name="research")
def research_command(
    ctx: typer.Context,
    topic: str = typer.Argument(..., help="The research topic"),
) -> None:
    """Phase 1 topic research (FR7)."""
    from sdlc.cli.research import run_research  # deferred per Architecture §488

    run_research(ctx=ctx, topic=topic)


@app.command(name="start")
def start_command(
    ctx: typer.Context,
    idea: str = typer.Argument(..., help="The idea text to begin Phase 1 with"),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress MockAIRuntime v1 stderr warning.",
    ),
) -> None:
    """Initiate Phase 1 product discovery (FR6)."""
    from sdlc.cli.start import run_start  # deferred per Architecture §488

    run_start(ctx=ctx, idea=idea, quiet=quiet)


@app.command(name="scan")
def scan_command(ctx: typer.Context) -> None:
    """Refresh state.json from the artifact tree (FR3)."""
    from sdlc.cli.scan import run_scan  # deferred per Architecture §488

    run_scan(ctx=ctx)


@app.command(name="verify")
def verify_command(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(
        ..., help="Repo-relative POSIX path under 01-Requirement/ to verify."
    ),
) -> None:
    """Verify a Phase 1 artifact (FR8, Story 2A.10)."""
    from sdlc.cli.verify import run_verify  # deferred per Architecture §488

    run_verify(ctx=ctx, artifact_id=artifact_id)


@app.command(name="epics")
def epics_command(ctx: typer.Context) -> None:
    """Generate epic JSON files from the draft PRD (FR9, Story 2A.11)."""
    from sdlc.cli.epics import run_epics  # deferred per Architecture §488

    run_epics(ctx=ctx)


@app.command(name="stories")
def stories_command(
    ctx: typer.Context,
    epic_id: str = typer.Argument(..., help="The EPIC-<slug> id to generate stories for"),
) -> None:
    """Generate story JSON files for a given epic (FR10, Story 2A.11)."""
    from sdlc.cli.stories import run_stories  # deferred per Architecture §488

    run_stories(ctx=ctx, epic_id=epic_id)


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
        None,
        "--filter-task",
        help="Restrict to entries matching this task-id (combined with --filter-agent as AND).",
    ),
    filter_agent: str | None = typer.Option(
        None,
        "--filter-agent",
        help="Restrict to entries from this agent (combined with --filter-task as AND).",
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Tail-follow streams; exit on Ctrl-C."
    ),
) -> None:
    """Tail journal + agent_runs.jsonl with filters (FR45, NFR-OBS-6).

    `--filter-task` and `--filter-agent` are intersected (AND-semantics);
    an entry is kept only if it satisfies every filter that is set.
    """
    from sdlc.cli.logs import run_logs  # deferred

    run_logs(ctx=ctx, filter_task=filter_task, filter_agent=filter_agent, follow=follow)


@app.command(name="rebuild-state")
def _rebuild_state_cmd(ctx: typer.Context) -> None:
    """Rebuild state.json from the journal (FR35)."""
    from sdlc.cli.rebuild_state import run_rebuild_state  # deferred per Architecture §488

    run_rebuild_state(ctx=ctx)


@app.command(name="signoff")
def signoff_command(
    ctx: typer.Context,
    phase: int = typer.Argument(..., help="Phase number to sign off (1 or 2)"),
) -> None:
    """Generate a phase signoff draft for human approval (FR11, Story 2A.12)."""
    from sdlc.cli.signoff import run_signoff  # deferred per Architecture §488

    run_signoff(ctx=ctx, phase=phase)


@app.command(name="ux")
def ux_command(ctx: typer.Context) -> None:
    """Initiate Phase 2 UX track (FR13)."""
    from sdlc.cli.ux import run_ux  # deferred per Architecture §488

    run_ux(ctx=ctx)


@app.command(name="architect")
def architect_command(ctx: typer.Context) -> None:
    """Initiate Phase 2 system architecture track (FR14)."""
    from sdlc.cli.architect import run_architect  # deferred per Architecture §488

    run_architect(ctx=ctx)


@app.command(name="bootstrap")
def bootstrap_command(ctx: typer.Context) -> None:
    """Initiate Phase 3 codebase scaffolding (FR15)."""
    from sdlc.cli.bootstrap import run_bootstrap  # deferred per Architecture §488

    run_bootstrap(ctx=ctx)


@app.command(name="trust-hooks")
def trust_hooks_command(ctx: typer.Context) -> None:
    """Record current hook file hashes to establish trust baseline (FR39)."""
    from sdlc.cli.trust_hooks import run_trust_hooks  # deferred per Architecture §488

    run_trust_hooks(ctx=ctx)


@app.command(name="hook-check")
def hook_check_command(ctx: typer.Context) -> None:
    """Run the engine hook chain against a HookPayload JSON (AC2, Story 2A.6)."""
    from sdlc.cli.hook_check import run_hook_check  # deferred per Architecture §488

    run_hook_check(ctx=ctx)


def _register_migrate_commands(app: typer.Typer) -> None:
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


_register_migrate_commands(app)

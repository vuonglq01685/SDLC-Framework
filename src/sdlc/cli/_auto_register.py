"""Registers the auto-loop (`auto`, FR19) and trace (`trace`, FR33) CLI commands.

Extracted from main.py to keep that module under the 400 LOC cap (code-review P1).
The two commands are grouped here because Story 4.1's `trace --correlation-id` mode
reconstructs an auto-loop iteration (AC4), tying the two surfaces together.
"""

from __future__ import annotations

import typer

__all__ = ("register_auto_commands",)


def register_auto_commands(app: typer.Typer) -> None:
    """Attach the `trace` and `auto` subcommands to the Typer app."""

    @app.command(name="trace")
    def trace_command(
        ctx: typer.Context,
        task_id: str | None = typer.Argument(
            None, help="Task identifier (EPIC-...-S<NN>-...-T<NN>-...)."
        ),
        correlation_id: str | None = typer.Option(
            None,
            "--correlation-id",
            help="Reconstruct one auto-loop iteration by its correlation_id (AC4) "
            "instead of by task-id.",
        ),
    ) -> None:
        """Reconstruct chronological history of a task or an auto-loop iteration (FR33)."""
        from sdlc.cli.trace import run_trace  # deferred per Architecture §488

        run_trace(ctx=ctx, task_id=task_id, correlation_id=correlation_id)

    @app.command(name="auto")
    def auto_command(
        ctx: typer.Context,
        allow_mock: bool = typer.Option(
            False,
            "--allow-mock",
            help="Acknowledge MockAIRuntime when SDLC_USE_MOCK_RUNTIME=1 (ADR-029).",
        ),
        max_iterations: int | None = typer.Option(
            None,
            "--max-iterations",
            min=1,
            help="Bound the loop to at most N iterations — a safety backstop until "
            "Layer-2 STOP triggers land (FR19).",
        ),
        confirm_tool_call: str | None = typer.Option(
            None,
            "--confirm-tool-call",
            help="Resume a halted high-risk tool call by its stable tool_call_id (Story 4.7).",
        ),
    ) -> None:
        """Run the autonomous auto-loop until STOP or no ready items (FR19, Story 4.1)."""
        from sdlc.cli.auto import run_auto  # deferred per Architecture §488

        run_auto(
            ctx=ctx,
            allow_mock=allow_mock,
            max_iterations=max_iterations,
            confirm_tool_call=confirm_tool_call,
        )

    @app.command(name="auto-mad")
    def auto_mad_command(
        ctx: typer.Context,
        allow_mock: bool = typer.Option(
            False,
            "--allow-mock",
            help="Acknowledge MockAIRuntime when SDLC_USE_MOCK_RUNTIME=1 (ADR-029).",
        ),
        max_iterations: int | None = typer.Option(
            None,
            "--max-iterations",
            min=1,
            help="Bound the mad-mode loop to at most N iterations.",
        ),
        confirm_tool_call: str | None = typer.Option(
            None,
            "--confirm-tool-call",
            help="Resume a halted high-risk tool call by its stable tool_call_id (Story 4.7).",
        ),
    ) -> None:
        """Run mad-mode auto-loop with auto-resolution of signoff/clarification STOPs (FR20)."""
        from sdlc.cli.auto import run_auto_mad  # deferred per Architecture §488

        run_auto_mad(
            ctx=ctx,
            allow_mock=allow_mock,
            max_iterations=max_iterations,
            confirm_tool_call=confirm_tool_call,
        )

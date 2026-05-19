"""`sdlc next` — select and advance the highest-priority ready item (FR18, Story 2A.18).

AC1/D1: module name next_.py (trailing underscore; `next` is a Python builtin).
AC2/D1: phase-aware resolver; does NOT drive from state.json (v1 projection has empty tasks).
AC3/D1: in-process run_task call (deferred import; soft dep on Story 2A.17).
No workflow YAML, no specialist, agents/index.yaml not touched.

DEBT: EPIC-2A-DEBT-NEXT-CONSUME-PROJECTION — refactor to consume state.json
  once EPIC-2A-DEBT-TASK-STATE-PROJECTION lands the task projection.
"""

from __future__ import annotations

from typing import Final

import typer

from sdlc.cli._next_resolver import _NextDecision, resolve_next
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import emit_error, emit_json
from sdlc.errors import SignoffError

_STATE_REL: Final[str] = ".claude/state/state.json"


def run_next(*, ctx: typer.Context) -> None:
    """Select and advance the highest-priority ready item (FR18)."""
    # Step 1 — resolve repo root
    root = _get_repo_root_or_cwd()

    # Step 2 — init guard (AC1)
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    # Step 3 — run the phase-aware resolver (AC2/D1)
    try:
        decision = resolve_next(root)
    except (SignoffError, OSError) as exc:
        emit_error(
            "ERR_SIGNOFF_READ_FAILED",
            f"signoff state could not be read: {exc}",
            ctx=ctx,
            details={"cause": str(exc)},
        )

    _handle_decision(decision, ctx=ctx)


def _json_mode(ctx: typer.Context) -> bool:
    """True when the global ``--json`` flag is set (mirrors ``output`` json detection)."""
    return bool(ctx.obj is not None and ctx.obj.get("json", False))


def _handle_decision(decision: _NextDecision, *, ctx: typer.Context) -> None:
    # Step 4 — Phase 3 task: auto-dispatch (AC3/D1)
    if decision.kind == "dispatch_task":
        task_id = decision.task_id
        if task_id is None:  # defensive — resolver guarantees task_id for dispatch_task
            emit_error(
                "ERR_INFRASTRUCTURE",
                "internal: dispatch_task decision is missing task_id",
                ctx=ctx,
                details={},
            )
        from sdlc.cli.task import run_task  # deferred; soft dep on Story 2A.17

        run_task(ctx=ctx, task_id=task_id)
        return

    # Step 5 — Phase 1/2 advance: print suggested command (AC4)
    # AC4: the printed line is human-readable on stdout; --json yields the envelope.
    if decision.kind == "run_command":
        if _json_mode(ctx):
            emit_json(
                "next",
                {
                    "next_action": "command",
                    "phase": decision.phase,
                    "suggested_command": decision.command,
                    "reason": decision.reason,
                },
                ctx=ctx,
            )
        else:
            typer.echo(f"sdlc next: run {decision.command}  ({decision.reason})")
        return

    # Step 6 — no ready items (AC5)
    # AC5: prints a reason string; --json yields the envelope.
    if _json_mode(ctx):
        emit_json(
            "next",
            {
                "next_action": "none",
                "reason": decision.reason,
                "blockers": decision.blockers,
            },
            ctx=ctx,
        )
    else:
        typer.echo(f"sdlc next: no ready items — {decision.reason}")

"""`sdlc auto` — autonomous auto-loop orchestrator (FR19, Story 4.1)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._runtime_selection import build_runtime, use_mock_runtime
from sdlc.cli.output import emit_error, emit_json
from sdlc.config.project import DEFAULT_PROJECT_YAML, load_project_config
from sdlc.dispatcher import DispatchResult
from sdlc.engine.auto_loop import DispatchFn, run_auto_loop
from sdlc.errors import ConfigError
from sdlc.runtime.abc import AIRuntime
from sdlc.specialists import load_registry
from sdlc.specialists.registry import SpecialistRegistry

_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_STATE_REL: Final[str] = ".claude/state/state.json"
_AGENTS_REL: Final[str] = ".claude/agents"
_RUNS_REL: Final[str] = "03-Implementation/agent_runs.jsonl"
_DEBT_ID: Final[str] = "EPIC-4-DEBT-AUTO-REAL-DISPATCH"


def _make_task_dispatch_fn(
    ctx: typer.Context, *, confirm_tool_call_id: str | None = None
) -> DispatchFn:
    async def _task_dispatch_fn(
        *,
        task_id: str,
        repo_root: Path,
        journal_path: Path,
        agent_runs_path: Path,
        runtime: AIRuntime,
        registry: SpecialistRegistry,
        correlation_id: str,
    ) -> DispatchResult | None:
        from sdlc.cli.task import run_task

        _ = (
            repo_root,
            journal_path,
            agent_runs_path,
            runtime,
            registry,
            correlation_id,
            confirm_tool_call_id,
        )
        run_task(ctx=ctx, task_id=task_id, allow_mock=True)
        return None

    return _task_dispatch_fn


def run_auto(
    *,
    ctx: typer.Context,
    allow_mock: bool = False,
    max_iterations: int | None = None,
    confirm_tool_call: str | None = None,
) -> None:
    """Run the autonomous auto-loop until STOP or no ready items."""
    _ = allow_mock
    if not use_mock_runtime():
        emit_error(
            "ERR_AUTO_LOOP_REAL_DISPATCH_DEFERRED",
            "/sdlc-auto cannot dispatch on the real runtime yet; use the mock runtime "
            "(SDLC_USE_MOCK_RUNTIME=1) until real auto-loop dispatch is wired. "
            f"Tracked as {_DEBT_ID}.",
            ctx=ctx,
            details={"debt": _DEBT_ID},
        )

    root = _get_repo_root_or_cwd()
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    journal_path = (root / _JOURNAL_REL).resolve()
    agent_runs_path = (root / _RUNS_REL).resolve()
    state_path = (root / _STATE_REL).resolve()
    registry = load_registry(root / _AGENTS_REL)

    try:
        project_cfg = load_project_config(root / DEFAULT_PROJECT_YAML)
        watchdog_timeout_minutes = project_cfg.watchdog_timeout_minutes
        auto_brainstorm = project_cfg.auto_brainstorm
    except ConfigError as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"project.yaml could not be read: {exc}",
            ctx=ctx,
            details={"path": str(root / DEFAULT_PROJECT_YAML)},
        )

    with tempfile.TemporaryDirectory() as tmp:
        runtime = build_runtime(fixtures_dir=Path(tmp))
        result = asyncio.run(
            run_auto_loop(
                root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                runtime=runtime,
                registry=registry,
                dispatch_fn=_make_task_dispatch_fn(ctx, confirm_tool_call_id=confirm_tool_call),
                state_path=state_path,
                max_iterations=max_iterations,
                watchdog_timeout_minutes=watchdog_timeout_minutes,
                auto_brainstorm=auto_brainstorm,
            )
        )

    if ctx.obj.get("json", False):
        emit_json(
            "auto",
            {
                "iterations": result.iterations,
                "last_action": result.last_action,
                "halted": result.halted,
                "stop_reason": result.stop_reason,
            },
            ctx=ctx,
        )


def run_auto_mad(
    *,
    ctx: typer.Context,
    allow_mock: bool = False,
    max_iterations: int | None = None,
    confirm_tool_call: str | None = None,
) -> None:
    """Run the auto-loop in mad-mode (YOLO auto-resolution of signoff/clarification STOPs)."""
    _ = allow_mock
    if not use_mock_runtime():
        emit_error(
            "ERR_AUTO_LOOP_REAL_DISPATCH_DEFERRED",
            "/sdlc-auto-mad cannot dispatch on the real runtime yet; use the mock runtime "
            "(SDLC_USE_MOCK_RUNTIME=1) until real auto-loop dispatch is wired. "
            f"Tracked as {_DEBT_ID}.",
            ctx=ctx,
            details={"debt": _DEBT_ID},
        )

    root = _get_repo_root_or_cwd()
    if not (root / _STATE_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    journal_path = (root / _JOURNAL_REL).resolve()
    agent_runs_path = (root / _RUNS_REL).resolve()
    state_path = (root / _STATE_REL).resolve()
    registry = load_registry(root / _AGENTS_REL)

    try:
        project_cfg = load_project_config(root / DEFAULT_PROJECT_YAML)
        watchdog_timeout_minutes = project_cfg.watchdog_timeout_minutes
        auto_brainstorm = project_cfg.auto_brainstorm
    except ConfigError as exc:
        emit_error(
            "ERR_USER_INPUT",
            f"project.yaml could not be read: {exc}",
            ctx=ctx,
            details={"path": str(root / DEFAULT_PROJECT_YAML)},
        )

    with tempfile.TemporaryDirectory() as tmp:
        runtime = build_runtime(fixtures_dir=Path(tmp))
        result = asyncio.run(
            run_auto_loop(
                root,
                journal_path=journal_path,
                agent_runs_path=agent_runs_path,
                runtime=runtime,
                registry=registry,
                dispatch_fn=_make_task_dispatch_fn(ctx, confirm_tool_call_id=confirm_tool_call),
                state_path=state_path,
                max_iterations=max_iterations,
                watchdog_timeout_minutes=watchdog_timeout_minutes,
                auto_brainstorm=auto_brainstorm,
                mad_mode=True,
            )
        )

    if ctx.obj.get("json", False):
        emit_json(
            "auto-mad",
            {
                "iterations": result.iterations,
                "last_action": result.last_action,
                "halted": result.halted,
                "stop_reason": result.stop_reason,
            },
            ctx=ctx,
        )

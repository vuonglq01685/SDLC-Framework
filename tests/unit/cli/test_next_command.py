"""Unit tests for cli/next_.py:run_next — AC1 + AC3-AC6 (Story 2A.18, Tasks 1 + 3)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_next(tmp_path: Path, *, json_out: bool = False) -> Any:
    args = ["--json", "next"] if json_out else ["next"]
    with unittest.mock.patch("sdlc.cli.next_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


# ---------------------------------------------------------------------------
# AC1 — Command registered
# ---------------------------------------------------------------------------


def test_next_command_registered() -> None:
    result = _runner.invoke(app, ["next", "--help"])
    assert result.exit_code == 0
    assert "next" in result.output.lower()


# ---------------------------------------------------------------------------
# AC1 — Init guard
# ---------------------------------------------------------------------------


def test_not_initialized_exits_nonzero(tmp_path: Path) -> None:
    r = _invoke_next(tmp_path)
    assert r.exit_code != 0
    assert "ERR_NOT_INITIALIZED" in r.output or "not initialized" in r.output


def test_not_initialized_json_envelope(tmp_path: Path) -> None:
    r = _invoke_next(tmp_path, json_out=True)
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_NOT_INITIALIZED"


# ---------------------------------------------------------------------------
# AC3 — dispatch_task branch: run_task called with selected task_id
# ---------------------------------------------------------------------------


def test_dispatch_task_calls_run_task(tmp_path: Path) -> None:
    """resolver returns dispatch_task → run_task is called with correct id."""
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="dispatch_task",
        task_id="EPIC-foo-S01-bar-T01-baz",
        command=None,
        phase=None,
        reason="phase 3 task ready",
        blockers={},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
        unittest.mock.patch("sdlc.cli.task.run_task") as mock_run_task,
    ):
        _invoke_next(tmp_path)
    mock_run_task.assert_called_once()
    call_kwargs = mock_run_task.call_args.kwargs
    assert call_kwargs["task_id"] == "EPIC-foo-S01-bar-T01-baz"


# ---------------------------------------------------------------------------
# AC4 — run_command branch: suggest command printed; exit 0; no dispatch
# ---------------------------------------------------------------------------


def test_run_command_prints_suggestion(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="run_command",
        task_id=None,
        command="/sdlc-architect",
        phase=2,
        reason="phase 2 not started",
        blockers={},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
    ):
        r = _invoke_next(tmp_path)
    assert r.exit_code == 0
    assert "/sdlc-architect" in r.output


def test_run_command_json_envelope(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="run_command",
        task_id=None,
        command="/sdlc-signoff 1",
        phase=1,
        reason="phase 1 unsigned",
        blockers={},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
    ):
        r = _invoke_next(tmp_path, json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["command"] == "next"
    assert data["next_action"] == "command"
    assert data["phase"] == 1
    assert data["suggested_command"] == "/sdlc-signoff 1"


def test_run_command_no_dispatch(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="run_command",
        task_id=None,
        command="/sdlc-architect",
        phase=2,
        reason="no arch",
        blockers={},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
        unittest.mock.patch("sdlc.cli.task.run_task") as mock_run_task,
    ):
        _invoke_next(tmp_path)
    mock_run_task.assert_not_called()


# ---------------------------------------------------------------------------
# AC5 — none branch: reason printed; exit 0
# ---------------------------------------------------------------------------


def test_none_branch_prints_reason(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="none",
        task_id=None,
        command=None,
        phase=None,
        reason="all tasks complete",
        blockers={"blocked_by_deps": 0, "awaiting_signoff": 0},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
    ):
        r = _invoke_next(tmp_path)
    assert r.exit_code == 0
    assert "all tasks complete" in r.output


def test_none_branch_json_envelope(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    from sdlc.cli._next_resolver import _NextDecision

    decision = _NextDecision(
        kind="none",
        task_id=None,
        command=None,
        phase=None,
        reason="2 tasks blocked by dependencies",
        blockers={"blocked_by_deps": 2, "awaiting_signoff": 0},
    )
    with (
        unittest.mock.patch("sdlc.cli.next_.resolve_next", return_value=decision),
    ):
        r = _invoke_next(tmp_path, json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["command"] == "next"
    assert data["next_action"] == "none"
    assert data["blockers"]["blocked_by_deps"] == 2

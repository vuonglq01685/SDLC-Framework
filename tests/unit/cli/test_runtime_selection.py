"""Unit tests for mock-vs-real runtime selection (Story 2B.1, ADR-029)."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli._runtime_selection import (
    build_runtime,
    enforce_allow_mock_gate,
    use_mock_runtime,
)
from sdlc.cli.main import app
from sdlc.runtime.claude import ClaudeAIRuntime
from sdlc.runtime.mock import MockAIRuntime

pytestmark = pytest.mark.unit

_runner = CliRunner()


def test_use_mock_runtime_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDLC_USE_MOCK_RUNTIME", raising=False)
    assert use_mock_runtime() is False


def test_use_mock_runtime_on_when_env_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    assert use_mock_runtime() is True


def test_build_runtime_selects_claude_when_mock_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SDLC_USE_MOCK_RUNTIME", raising=False)
    runtime = build_runtime(fixtures_dir=tmp_path)
    assert isinstance(runtime, ClaudeAIRuntime)


def test_build_runtime_selects_mock_when_env_on(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    runtime = build_runtime(fixtures_dir=tmp_path)
    assert isinstance(runtime, MockAIRuntime)


def test_enforce_allow_mock_gate_exits_without_flag_outside_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    ctx = typer.Context(command=typer.core.TyperCommand("x"))
    ctx.ensure_object(dict)
    with unittest.mock.patch("sdlc.cli._runtime_selection.emit_error") as mock_err:
        enforce_allow_mock_gate(allow_mock=False, ctx=ctx)
    mock_err.assert_called_once()
    assert mock_err.call_args.args[0] == "ERR_USER_INPUT"


def test_enforce_allow_mock_gate_returns_true_when_allow_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    ctx = typer.Context(command=typer.core.TyperCommand("x"))
    ctx.ensure_object(dict)
    assert enforce_allow_mock_gate(allow_mock=True, ctx=ctx) is True


def test_bootstrap_mock_without_allow_mock_fails_outside_pytest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["--json", "bootstrap"])
    assert result.exit_code == 1
    assert "allow-mock" in (result.stderr or result.stdout).lower()

"""Unit tests for `sdlc start` (Story 2A.8, Task 4.1)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

_runner = CliRunner()

pytestmark = pytest.mark.unit


def test_start_subcommand_in_help() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout


def test_start_missing_idea_exits_2() -> None:
    result = _runner.invoke(app, ["start"])
    assert result.exit_code == 2


def test_start_empty_idea_returns_user_input_error() -> None:
    """Empty-string idea hits the ERR_USER_INPUT branch (exit 1) in run_start."""
    result = _runner.invoke(app, ["start", ""])
    assert result.exit_code == 1
    out = result.stderr + result.stdout
    assert "idea text must be non-empty" in out or "ERR_USER_INPUT" in out


def test_start_not_initialized_exits_1(tmp_path: Path) -> None:
    with unittest.mock.patch("sdlc.cli.start._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["start", "hello"])
    assert result.exit_code == 1
    assert "not initialized" in result.stderr.lower() or "not initialized" in result.stdout.lower()


def test_start_product_exists_exits_1(tmp_path: Path) -> None:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"schema_version":1}\n', encoding="utf-8")
    (state_dir / "journal.log").touch()
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True)
    (req / "01-PRODUCT.md").write_text("# exists\n", encoding="utf-8")
    with unittest.mock.patch("sdlc.cli.start._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["start", "new idea"])
    assert result.exit_code == 1
    out = result.stderr + result.stdout
    assert "ERR_PHASE1_PRODUCT_EXISTS" in out or "already exists" in out.lower()


def test_start_json_success_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    with unittest.mock.patch("sdlc.cli.start._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["--json", "start", "JSON mode idea"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload.get("command") == "start"
    assert payload.get("outcome") == "success"
    assert payload.get("phase") == 1
    assert "01-Requirement/01-PRODUCT.md" in (payload.get("artifact") or "")

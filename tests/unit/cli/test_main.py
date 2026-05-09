"""Unit tests for sdlc.cli.main Typer app (AC6.3, AC7.4)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

import sdlc
from sdlc.cli.main import app
from sdlc.state import State, state_to_canonical_bytes

runner = CliRunner()


@pytest.mark.unit
def test_main_app_has_init_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout


@pytest.mark.unit
def test_main_app_version_flag_prints_version_and_exits_zero() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert sdlc.__version__ in result.stdout
    # AC1.2: stdout MUST contain exactly one line `sdlc <version>`, no leading/
    # trailing blank lines, no ANSI escape sequences. CliRunner strips no
    # decoration; if rich/typer ever introduces colorisation on --version, this
    # test fails loudly.
    assert "\x1b[" not in result.stdout, "ANSI escape detected in --version output"
    body = result.stdout.strip("\n")
    assert "\n" not in body, f"--version emitted multiple lines: {result.stdout!r}"
    assert body == f"sdlc {sdlc.__version__}", f"--version body mismatch: {body!r}"


@pytest.mark.unit
def test_main_app_has_scan_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.stdout


@pytest.mark.unit
def test_main_app_has_status_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "status" in result.stdout


@pytest.mark.unit
def test_main_app_no_color_flag_recognized() -> None:
    result = runner.invoke(app, ["--no-color", "--version"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_main_app_json_flag_emits_json_for_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    # _version_callback inspects sys.argv directly (eager flag fires before _root sets ctx.obj)
    monkeypatch.setattr(sys, "argv", ["sdlc", "--json", "--version"])
    result = runner.invoke(app, ["--json", "--version"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "version"
    assert payload["version"] == sdlc.__version__


@pytest.mark.unit
def test_no_color_env_var_disables_color(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_bytes(state_to_canonical_bytes(State()))
    (state_dir / "journal.log").touch()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=tmp_path):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout


@pytest.mark.unit
def test_main_app_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # click 8.x convention: invoking a Group with no subcommand exits 2 even
    # when `no_args_is_help=True` prints the help text — this signals "missing
    # command" to shells. The AC1 "And" text was updated (Story 1.16 P10
    # review patch) from "exits 0" to "exits 2" to match click semantics. If a
    # future click/typer upgrade changes this, this test fails loudly and we
    # decide whether to update the AC or shim the exit code.
    assert result.exit_code == 2, (
        f"Expected click missing-command exit 2; got {result.exit_code}. stdout={result.stdout!r}"
    )
    assert "Usage:" in result.stdout

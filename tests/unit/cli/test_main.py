"""Unit tests for sdlc.cli.main Typer app (AC6.3)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import sdlc
from sdlc.cli.main import app

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
    assert body == f"sdlc {sdlc.__version__}", (
        f"--version body mismatch: {body!r}"
    )


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
        f"Expected click missing-command exit 2; got {result.exit_code}. "
        f"stdout={result.stdout!r}"
    )
    assert "Usage:" in result.stdout

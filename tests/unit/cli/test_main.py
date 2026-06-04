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
def test_main_app_has_trace_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "trace" in result.stdout


@pytest.mark.unit
def test_main_app_has_replay_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "replay" in result.stdout


@pytest.mark.unit
def test_main_app_has_logs_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "logs" in result.stdout


@pytest.mark.unit
def test_main_app_trace_requires_task_id() -> None:
    result = runner.invoke(app, ["trace"])
    assert result.exit_code != 0
    assert "missing" in result.output.lower() or "argument" in result.output.lower()


@pytest.mark.unit
def test_main_app_replay_requires_line_spec() -> None:
    result = runner.invoke(app, ["replay"])
    assert result.exit_code != 0
    assert "missing" in result.output.lower() or "argument" in result.output.lower()


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


# ---------------------------------------------------------------------------
# migrate-vN dynamic command registration (Story 1.19 AC7.5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def testregister_migrate_commands_adds_migrate_v2_when_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """register_migrate_commands must add a migrate-v<N> subcommand per discovered script."""
    import typer as _typer

    from sdlc.cli.main import register_migrate_commands

    test_app = _typer.Typer()
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2])
    register_migrate_commands(test_app)

    names = [cmd.name for cmd in test_app.registered_commands]
    assert "migrate-v2" in names


@pytest.mark.unit
def testregister_migrate_commands_no_op_when_no_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no discovered migrations (v1 state), no migrate-vN commands are registered."""
    import typer as _typer

    from sdlc.cli.main import register_migrate_commands

    test_app = _typer.Typer()
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [])
    register_migrate_commands(test_app)

    assert test_app.registered_commands == []


@pytest.mark.unit
def testregister_migrate_commands_registers_multiple_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import typer as _typer

    from sdlc.cli.main import register_migrate_commands

    test_app = _typer.Typer()
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2, 3, 10])
    register_migrate_commands(test_app)

    names = {cmd.name for cmd in test_app.registered_commands}
    assert names == {"migrate-v2", "migrate-v3", "migrate-v10"}


@pytest.mark.unit
def test_migrate_command_help_text_includes_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each dynamically registered migrate-vN command must include the version in its docstring."""
    import typer as _typer

    from sdlc.cli.main import register_migrate_commands

    test_app = _typer.Typer()
    monkeypatch.setattr("sdlc.migrations.discover_migrations", lambda: [2, 3])
    register_migrate_commands(test_app)

    for cmd in test_app.registered_commands:
        assert cmd.name is not None
        version_str = cmd.name.replace("migrate-v", "")
        doc = (cmd.help or "") or (getattr(cmd.callback, "__doc__", "") or "")
        assert version_str in doc, f"{cmd.name} docstring/help missing version {version_str!r}"


@pytest.mark.unit
def test_main_app_rebuild_state_command_is_registered() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rebuild-state" in result.stdout


@pytest.mark.unit
def test_main_app_rebuild_state_short_help_text() -> None:
    result = runner.invoke(app, ["rebuild-state", "--help"])
    assert result.exit_code == 0
    # The command name "rebuild-state" trivially produces "rebuild" in --help output;
    # tighten to the docstring's actual content. AC3.2 docstring: "Rebuild state.json
    # from the journal (FR35)." — both "state.json" and "journal" must appear.
    output_lower = result.output.lower()
    assert "state.json" in output_lower, (
        f"rebuild-state --help missing 'state.json' in docstring; got:\n{result.output}"
    )
    assert "journal" in output_lower, (
        f"rebuild-state --help missing 'journal' in docstring; got:\n{result.output}"
    )
    assert "fr35" in output_lower, (
        f"rebuild-state --help missing 'FR35' anchor in docstring; got:\n{result.output}"
    )

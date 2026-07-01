"""CLI tests for `sdlc dashboard` (Story 5.1 AC1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestDashboardCli:
    def test_help_lists_dashboard_command(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "dashboard" in result.stdout

    def test_dashboard_invokes_serve(self, runner: CliRunner, tmp_path: Path) -> None:
        with (
            patch("sdlc.cli._paths.get_repo_root_or_cwd", return_value=tmp_path),
            patch("sdlc.dashboard.server.serve_dashboard") as serve_mock,
        ):
            serve_mock.side_effect = KeyboardInterrupt
            result = runner.invoke(app, ["dashboard", "--port", "9999"])
        assert result.exit_code == 0
        # Story 5.13 D1: run_dashboard now injects a git-log provider (git_dora_log bound
        # to repo_root) so the dashboard server stays subprocess-free / cli-free.
        serve_mock.assert_called_once_with(repo_root=tmp_path, port=9999, git_log_provider=ANY)
        assert "serving on http://127.0.0.1:9999" in result.stdout

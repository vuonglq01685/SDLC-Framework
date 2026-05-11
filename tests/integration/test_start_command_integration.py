"""Integration tests for `sdlc start` CLI end-to-end (Story 2A.8, P44).

These tests invoke `init` followed by `start` through the Typer CLI surface,
exercising the full command pipeline against a real tmp_path repo. Moved from
``tests/unit/cli/test_start_command.py`` since the unit suite is reserved for
pure-CLI surface checks (help, argument parsing, single-call exit codes).
"""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

_runner = CliRunner()

pytestmark = pytest.mark.integration


def test_start_quiet_suppresses_mock_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With --quiet, MockAIRuntime v1 warning must not appear on stderr."""
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    with unittest.mock.patch("sdlc.cli.start._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["start", "--quiet", "Build a thing"])
    assert result.exit_code == 0
    assert "MockAIRuntime" not in result.stderr

"""Integration tests: every subcommand x every no-color signal emits zero ANSI (AC7.3)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH — skipping subprocess e2e test",
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_COMMANDS: list[list[str]] = [
    ["sdlc", "init"],
    ["sdlc", "status"],
]


def _bootstrap(tmp_path: Path) -> None:
    subprocess.run(["uv", "run", "sdlc", "init"], cwd=tmp_path, capture_output=True, check=False)


@_SKIP_NO_UV
@pytest.mark.parametrize("cmd_args", _COMMANDS, ids=lambda c: c[-1])
def test_no_color_flag_suppresses_ansi(cmd_args: list[str], tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    result = subprocess.run(
        ["uv", "run", cmd_args[0], "--no-color", *cmd_args[1:]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert _ANSI_RE.search(result.stdout) is None, (
        f"ANSI escapes in stdout for {cmd_args} --no-color: {result.stdout!r}"
    )
    assert _ANSI_RE.search(result.stderr) is None, (
        f"ANSI escapes in stderr for {cmd_args} --no-color: {result.stderr!r}"
    )


@_SKIP_NO_UV
@pytest.mark.parametrize("cmd_args", _COMMANDS, ids=lambda c: c[-1])
def test_no_color_env_var_suppresses_ansi(cmd_args: list[str], tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    env = {"NO_COLOR": "1"}
    result = subprocess.run(
        ["uv", "run", *cmd_args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, **env},
    )
    assert _ANSI_RE.search(result.stdout) is None, (
        f"ANSI escapes in stdout with NO_COLOR=1 for {cmd_args}: {result.stdout!r}"
    )

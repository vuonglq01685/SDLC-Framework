"""End-to-end integration tests for `sdlc init` and `sdlc --version` (AC6.4)."""

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


@_SKIP_NO_UV
def test_sdlc_init_via_subprocess_creates_layout(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "sdlc", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"sdlc init failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (tmp_path / ".claude" / "state" / "state.json").exists()
    assert (tmp_path / ".claude" / "state" / "journal.log").exists()
    for tree in ("agents", "commands", "hooks", "workflows", "memory", "skills"):
        assert (tmp_path / ".claude" / tree).is_dir()
    for phase in ("01-Requirement", "02-Architecture", "03-Implementation"):
        assert (tmp_path / phase).is_dir()


@_SKIP_NO_UV
def test_sdlc_version_via_subprocess_prints_version(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "sdlc", "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"sdlc --version failed: {result.stderr}"
    # AC1.2: exactly one line, no leading/trailing blank lines, no ANSI escapes.
    assert "\x1b[" not in result.stdout, (
        f"ANSI escape detected in --version output: {result.stdout!r}"
    )
    body = result.stdout.strip("\n")
    assert "\n" not in body, f"--version emitted multiple lines: {result.stdout!r}"
    assert re.match(r"^sdlc \d+\.\d+\.\d+$", body), (
        f"Unexpected --version output: {result.stdout!r}"
    )

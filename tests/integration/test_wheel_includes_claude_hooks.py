"""Wheel packaging assertion: ``sdlc/claude_hooks/pre_tool_use.py`` ships (AC8, Story 2A.6).

Builds the wheel via ``uv build --wheel`` (``python -m build`` fallback) and asserts
the Claude-side hook is present so that ``sdlc init`` can copy it into ``.claude/hooks/``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SKIP_NO_BUILDER = pytest.mark.skipif(
    shutil.which("uv") is None and shutil.which("python") is None,
    reason="neither uv nor python available — cannot build wheel",
)

_REQUIRED_CLAUDE_HOOKS = frozenset(
    {
        "sdlc/claude_hooks/__init__.py",
        "sdlc/claude_hooks/pre_tool_use.py",
    }
)


def _build_wheel(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("uv") is not None:
        cmd = ["uv", "build", "--wheel", "--out-dir", str(out_dir)]
    else:
        cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)]
    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"wheel build failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    wheels = list(out_dir.glob("sdlc_framework-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel; got {wheels}"
    return wheels[0]


@_SKIP_NO_BUILDER
def test_wheel_ships_claude_hooks(tmp_path: Path) -> None:
    """The 2A.6 wheel must contain both claude_hooks files (AC8 last-And)."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = frozenset(zf.namelist())
    missing = _REQUIRED_CLAUDE_HOOKS - names
    assert not missing, f"wheel missing claude_hooks files: {missing}"

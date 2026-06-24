"""Wheel packaging assertions for dashboard static assets (Story 5.3)."""

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

_EXPECTED_DASHBOARD_STATIC = frozenset(
    {
        "sdlc/dashboard/static/icons/sprite.svg",
        "sdlc/dashboard/static/fonts/OFL.txt",
        "sdlc/dashboard/static/fonts/fraunces-400.woff2",
        "sdlc/dashboard/static/fonts/fraunces-500.woff2",
        "sdlc/dashboard/static/fonts/fraunces-600.woff2",
        "sdlc/dashboard/static/fonts/inter-300.woff2",
        "sdlc/dashboard/static/fonts/inter-400.woff2",
        "sdlc/dashboard/static/fonts/inter-500.woff2",
        "sdlc/dashboard/static/fonts/inter-600.woff2",
        "sdlc/dashboard/static/fonts/inter-700.woff2",
        "sdlc/dashboard/static/fonts/jetbrains-mono-400.woff2",
        "sdlc/dashboard/static/fonts/jetbrains-mono-500.woff2",
        "sdlc/dashboard/static/fonts/jetbrains-mono-600.woff2",
        "sdlc/dashboard/static/styles/focus-motion.css",
        "sdlc/dashboard/static/fixtures/reduced-motion-pulse.html",
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
def test_wheel_ships_self_hosted_fonts_and_sprite(tmp_path: Path) -> None:
    """Story 5.3: every force-included font + sprite must appear in the wheel."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = {Path(n).as_posix() for n in zf.namelist()}
    missing = _EXPECTED_DASHBOARD_STATIC - names
    assert not missing, f"wheel missing dashboard static assets: {sorted(missing)}"

"""Wheel-listing assertion test (AC4.4 — Story 1.16).

Builds the v1.16 wheel via `uv build --wheel` (or `python -m build --wheel`
fallback) and asserts the wheel manifest matches the AC4.4 contract:

  - Python source modules (`sdlc/**/*.py`) ship freely — the wheel must
    contain every module the runtime imports (`cli`, `state`, `journal`,
    `engine`, `errors`, `ids`, `runtime`, `concurrency`, `config`,
    `contracts`).
  - `.gitkeep` markers under each force-include tree are permitted (ADR-019
    §3 — required so hatch's force-include succeeds when the tree is
    otherwise empty).
  - **No content files** (`*.md`, `*.json`, `*.yaml`, `*.yml`, `*.toml`,
    `*.txt`, `*.csv`) ship outside `.dist-info/`. Future stories drop
    real content into `src/sdlc/<tree>/` and bump this test's expectations.

Any drift — a stray `agents/spec.md` or a missing `cli/init.py` — fails
the gate.
"""

from __future__ import annotations

import re
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

# Trees that ship as force-include in v1.16 — each contributes ONE `.gitkeep`
# marker to the wheel until real content lands in later stories.
_EXPECTED_GITKEEP_TREES = (
    "agents",
    "commands",
    "hooks",
    "workflows",
    "memory",
    "skills",
    "dashboard/static",
)

# CLI module files that MUST ship in v1.16. Story 1.17+ may ADD to this set;
# this test enforces "must include" semantics (drift surfaces in review).
_REQUIRED_CLI_FILES = frozenset(
    {
        "sdlc/__init__.py",
        "sdlc/cli/__init__.py",
        "sdlc/cli/exit_codes.py",
        "sdlc/cli/init.py",
        "sdlc/cli/main.py",
        "sdlc/cli/output.py",
        "sdlc/cli/version.py",
    }
)

# Suffixes that indicate "content" — would only be legitimate in future
# stories that actually ship runtime content under sdlc/<tree>/. v1.16 must
# not ship any of these outside .dist-info/.
_CONTENT_SUFFIXES = frozenset(
    {".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".csv"}
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
def test_wheel_ships_required_cli_modules(tmp_path: Path) -> None:
    """The v1.16 wheel must contain every CLI entrypoint module."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    missing = _REQUIRED_CLI_FILES - names
    assert not missing, f"wheel missing required cli modules: {missing}"


@_SKIP_NO_BUILDER
def test_wheel_ships_gitkeep_markers_for_force_include_trees(tmp_path: Path) -> None:
    """ADR-019 §3 — each force-include tree contains a `.gitkeep` marker in v1.16."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    expected = {f"sdlc/{tree}/.gitkeep" for tree in _EXPECTED_GITKEEP_TREES}
    missing = expected - names
    assert not missing, f"wheel missing required .gitkeep markers: {missing}"


@_SKIP_NO_BUILDER
def test_wheel_does_not_ship_content_files(tmp_path: Path) -> None:
    """AC4.4 — v1.16 ships NO content files (`.md`, `.json`, `.yaml`, …) outside `.dist-info/`.

    Catches accidental leakage from future stories: if Story 2A-2 lands
    `agents/index.yaml` and the source-tree merge bleeds into v1.16, this
    test fails before the wheel ships.
    """
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = sorted(zf.namelist())

    leaks = [
        n
        for n in names
        if not n.endswith("/")
        and ".dist-info/" not in n
        and Path(n).suffix in _CONTENT_SUFFIXES
    ]
    assert not leaks, (
        f"AC4.4 violation — v1.16 wheel ships content files outside .dist-info/: {leaks}"
    )


@_SKIP_NO_BUILDER
def test_wheel_dist_info_present(tmp_path: Path) -> None:
    """Sanity: wheel contains a well-formed `.dist-info/METADATA`."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert any(re.match(r"sdlc_framework-.*\.dist-info/METADATA$", n) for n in names), (
        f".dist-info/METADATA missing from wheel: {names}"
    )

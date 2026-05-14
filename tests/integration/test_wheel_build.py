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

# Suffixes that indicate "content" — must not bleed into the wheel accidentally.
# Intentionally-shipped content files are listed in _ALLOWED_CONTENT_FILES.
_CONTENT_SUFFIXES = frozenset({".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".csv"})

# Files explicitly allowed by story ACs.
# Story 2A.2: empty agents manifest stub.
# Story 2A.3+: phase1 specialist markdown (devil-advocate, product-strategist,
#   requirement-synthesizer, technical-researcher).
# Story 2A.9: /sdlc-start slash-command + workflow YAML.
# Story 2A.10: /sdlc-verify slash-command + workflow YAML + artifact-verifier specialist.
# P-R18: store as POSIX-normalized strings; comparisons normalize via Path.as_posix()
# so wheel name variants (`./sdlc/...`, backslashes on Windows builders, etc.) all
# resolve to the canonical form before allowlist lookup.
_ALLOWED_CONTENT_FILES = frozenset(
    {
        # Story 2A.2 — empty manifest stub must ship.
        Path("sdlc/agents/index.yaml").as_posix(),
        # Story 2A.10 — artifact-verifier specialist stub.
        Path("sdlc/agents/phase1/artifact-verifier.md").as_posix(),
        # Story 2A.8 — phase 1 specialist stubs (Story 2A.9 backfill from PR scope).
        Path("sdlc/agents/phase1/devil-advocate.md").as_posix(),
        Path("sdlc/agents/phase1/product-strategist.md").as_posix(),
        Path("sdlc/agents/phase1/requirement-synthesizer.md").as_posix(),
        Path("sdlc/agents/phase1/technical-researcher.md").as_posix(),
        # Story 2A.8 — /sdlc-start command + workflow YAML (2A.9 backfill).
        Path("sdlc/commands/sdlc-start.md").as_posix(),
        Path("sdlc/workflows_yaml/sdlc-start.yaml").as_posix(),
        # Story 2A.9 — /sdlc-research command + workflow YAML.
        Path("sdlc/commands/sdlc-research.md").as_posix(),
        Path("sdlc/workflows_yaml/sdlc-research.yaml").as_posix(),
        # Story 2A.10 — /sdlc-verify command + workflow YAML.
        Path("sdlc/commands/sdlc-verify.md").as_posix(),
        Path("sdlc/workflows_yaml/sdlc-verify.yaml").as_posix(),
        # Story 2A.11 — /sdlc-epics + /sdlc-stories specialist stubs, commands, workflows.
        Path("sdlc/agents/phase1/epic-generator.md").as_posix(),
        Path("sdlc/agents/phase1/story-writer.md").as_posix(),
        Path("sdlc/commands/sdlc-epics.md").as_posix(),
        Path("sdlc/commands/sdlc-stories.md").as_posix(),
        Path("sdlc/workflows_yaml/sdlc-epics.yaml").as_posix(),
        Path("sdlc/workflows_yaml/sdlc-stories.yaml").as_posix(),
    }
)


def _ensure_allowed_paths_exist_in_source(repo_root: Path) -> None:
    """P29 (code review): the allowlist is the wheel-content contract — a typo
    silently widens the surface. Guard against typos by asserting every entry
    actually exists in the source tree before the test relies on it.
    """
    missing = [p for p in _ALLOWED_CONTENT_FILES if not (repo_root / "src" / p).is_file()]
    assert not missing, f"allowlist entries missing from source tree: {missing}"


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
    """No accidental content files ship in the wheel outside of intentional allowlist.

    Story 2A.2 explicitly ships `agents/index.yaml` (empty manifest stub, per AC1/AC3).
    That file is in _ALLOWED_CONTENT_FILES. All other content-suffix files are leaks.
    """
    # P29 (code review): allowlist is the wheel-content contract — a typo
    # silently widens the surface. Verify every entry exists in source first.
    _ensure_allowed_paths_exist_in_source(Path(__file__).resolve().parents[2])
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = sorted(zf.namelist())

    leaks = [
        n
        for n in names
        if not n.endswith("/")
        and ".dist-info/" not in n
        and Path(n).suffix in _CONTENT_SUFFIXES
        and Path(n).as_posix() not in _ALLOWED_CONTENT_FILES
    ]
    assert not leaks, f"Wheel ships unexpected content files outside .dist-info/: {leaks}"


@_SKIP_NO_BUILDER
def test_wheel_dist_info_present(tmp_path: Path) -> None:
    """Sanity: wheel contains a well-formed `.dist-info/METADATA`."""
    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert any(re.match(r"sdlc_framework-.*\.dist-info/METADATA$", n) for n in names), (
        f".dist-info/METADATA missing from wheel: {names}"
    )

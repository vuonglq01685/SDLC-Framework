"""Deterministic, ambient-tool-independent subprocess-CLI helpers for e2e/parity tests.

Subprocess e2e/parity tests run the CLI with ``cwd`` set to a throwaway temp repo. A bare
``uv run sdlc`` (or the production hook's internal ``["sdlc", ...]`` dispatch) then resolves
``sdlc`` from PATH and can hit a stale ``uv tool install``'d copy instead of THIS project's
source — silently testing the wrong code (root cause of a whole class of phantom failures).

  * :func:`sdlc_uv_argv` pins ``uv run --project <repo-root> sdlc`` so uv uses this project's
    editable environment regardless of the subprocess cwd.
  * :func:`venv_path_env` prepends the active venv's bin dir to ``PATH`` so a subprocess whose
    OWN code shells out to a bare ``sdlc`` (the production ``claude_hooks/pre_tool_use.py``
    hook) resolves the editable CLI rather than an ambient tool.

This module lives directly under ``tests/`` and is importable as ``import _clihelper`` because
``conftest.py`` puts the ``tests/`` directory on ``sys.path``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# tests/_clihelper.py -> repo root is the parent of tests/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# pytest runs under the project venv, so sys.executable is <venv>/bin/python; its dir holds `sdlc`.
# NOTE: do NOT .resolve() — the venv python is a symlink to the base interpreter, whose bin dir has
# no console scripts. The unresolved parent is the venv bin dir that holds the editable `sdlc`.
VENV_BIN = Path(sys.executable).parent


def uv_run_argv(*args: str) -> list[str]:
    """argv to run any project entry point via ``uv run --project <repo>`` (cwd-independent)."""
    return ["uv", "run", "--project", str(PROJECT_ROOT), *args]


def sdlc_uv_argv(*args: str) -> list[str]:
    """argv to invoke this project's ``sdlc`` CLI deterministically against live source."""
    return uv_run_argv("sdlc", *args)


def venv_path_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an env mapping with the active venv bin prepended to ``PATH``.

    For subprocesses whose code shells out to a bare ``sdlc`` on PATH (the production
    ``pre_tool_use.py`` hook), this pins that resolution to the editable venv CLI so the test
    exercises live source instead of whatever ``sdlc`` happens to be installed globally.
    """
    env = dict(os.environ if base is None else base)
    env["PATH"] = f"{VENV_BIN}{os.pathsep}{env.get('PATH', '')}"
    return env

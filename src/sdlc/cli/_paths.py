"""Shared path helpers for `cli/` subcommands.

Factored from `cli/init.py`, `cli/scan.py`, and `cli/status.py` (Story 1.17 review)
so all subcommands resolve `repo_root` identically and the timeout / fallback policy
lives in one place.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

_GIT_TIMEOUT_SECONDS: Final[float] = 5.0


def get_repo_root_or_cwd() -> Path:
    """Return the git repo root, falling back to cwd if git is absent or unavailable.

    Timeout is intentionally short (5s): a healthy `git rev-parse` completes in
    tens of milliseconds; anything slower is a hung filesystem or missing git
    and we want to fall through to cwd quickly.
    """
    cwd = Path.cwd().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        # FileNotFoundError is a subclass of OSError, no need to list it separately.
        return cwd
    if result.returncode == 0:
        top = result.stdout.strip()
        if top:
            return Path(top).resolve()
    return cwd

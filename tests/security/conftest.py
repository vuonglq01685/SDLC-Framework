"""Shared pytest fixtures and import-path setup for `tests/security/`.

P8 (Story 2B.5 review): prepend `scripts/` to `sys.path` here rather than
relying on `scripts/check_boundary_line_presence.py` mutating it as an import
side effect. Keeps script-as-CLI and script-as-test-import surfaces decoupled.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

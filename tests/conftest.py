"""Pytest configuration: add scripts/ to sys.path for test imports."""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable so tests can do `import check_module_boundaries`.
_scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

"""Detection skips file symlinks (Story 3.7 / CR3.2-W1)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from sdlc.adopt.passes.detection import detect_existing

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("symlink fixtures are POSIX-only (ADR-034)", allow_module_level=True)

pytestmark = pytest.mark.unit


def test_detection_skips_symlink_file_entries(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    real = tmp_path / "docs" / "architecture.md"
    real.write_text("# Architecture\n\n## ADR-001\n\nC4 diagram.\n", encoding="utf-8")
    link = tmp_path / "README.md"
    if link.exists():
        link.unlink()
    os.symlink("docs/architecture.md", link)
    found = detect_existing(tmp_path)
    paths = {a.path for a in found}
    assert "README.md" not in paths
    assert "docs/architecture.md" in paths

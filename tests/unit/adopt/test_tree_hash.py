"""Unit tests for adopt.tree_hash (Story 3.7, D4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.adopt.tree_hash import compute_source_tree_hash

pytestmark = pytest.mark.unit


def test_tree_hash_changes_when_file_content_changes(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "a.py"
    f.write_text("a = 1\n", encoding="utf-8")
    h1 = compute_source_tree_hash(tmp_path)
    f.write_text("a = 2\n", encoding="utf-8")
    h2 = compute_source_tree_hash(tmp_path)
    assert h1 != h2


def test_tree_hash_stable_when_only_claude_changes(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    h1 = compute_source_tree_hash(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    (tmp_path / ".claude" / "state" / "adopt-report.json").write_text("{}", encoding="utf-8")
    h2 = compute_source_tree_hash(tmp_path)
    assert h1 == h2

"""Unit tests for ``_next_research_path`` (Story 2A.9, AC3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli.research import _next_research_path
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit


def test_empty_dir_returns_base(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    assert _next_research_path("x", research_dir=d) == d / "x.md"


def test_base_exists_returns_two(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    (d / "x.md").write_text("a", encoding="utf-8")
    assert _next_research_path("x", research_dir=d) == d / "x-2.md"


def test_base_and_two_returns_three(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    (d / "x.md").write_text("a", encoding="utf-8")
    (d / "x-2.md").write_text("b", encoding="utf-8")
    assert _next_research_path("x", research_dir=d) == d / "x-3.md"


def test_gap_filled_at_two(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    (d / "x.md").write_text("a", encoding="utf-8")
    (d / "x-3.md").write_text("b", encoding="utf-8")
    assert _next_research_path("x", research_dir=d) == d / "x-2.md"


def test_exhausted_raises(tmp_path: Path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    (d / "x.md").write_text("a", encoding="utf-8")
    for n in range(2, 1000):
        (d / f"x-{n}.md").write_text("z", encoding="utf-8")
    with pytest.raises(WorkflowError, match="exhausted"):
        _next_research_path("x", research_dir=d)


def test_dir_missing_returns_base(tmp_path: Path) -> None:
    d = tmp_path / "missing"
    assert _next_research_path("x", research_dir=d) == d / "x.md"

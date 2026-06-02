"""Unit tests for the adopt source-untouched guard (Story 3.1, AC7).

3.1 scope: the orchestrator writes ONLY under `.claude/`. Every write target is
pre-guarded by `assert_path_under_claude`, which raises `AdoptError` (ERR_ADOPT,
exit 2) on any path outside `root/.claude/`. The exhaustive porcelain + tree-hash
property + mutation gate is Story 3.7 — `assert_source_untouched` is the typed seam
3.7 will harden.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.adopt.invariant import assert_path_under_claude, assert_source_untouched
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit


def test_path_inside_claude_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "state" / "adopt-report.json"
    # does not raise
    assert_path_under_claude(tmp_path, target)


def test_path_outside_claude_raises_adopt_error(tmp_path: Path) -> None:
    target = tmp_path / "src" / "main.py"
    with pytest.raises(AdoptError) as exc_info:
        assert_path_under_claude(tmp_path, target)
    assert exc_info.value.code == "ERR_ADOPT"


def test_path_traversal_out_of_claude_raises(tmp_path: Path) -> None:
    """A `.claude/../src` path that escapes the sandbox via traversal is rejected."""
    target = tmp_path / ".claude" / ".." / "src" / "evil.py"
    with pytest.raises(AdoptError):
        assert_path_under_claude(tmp_path, target)


def test_claude_dir_itself_is_allowed(tmp_path: Path) -> None:
    assert_path_under_claude(tmp_path, tmp_path / ".claude")


def test_assert_source_untouched_seam_is_callable(tmp_path: Path) -> None:
    """The public seam (architecture.md:1069) exists and is a no-op in 3.1 (3.7 hardens it)."""
    assert assert_source_untouched(tmp_path) is None

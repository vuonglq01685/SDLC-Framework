"""Unit tests for adopt.source_tree (Story 3.7, AC3)."""

from __future__ import annotations

import pytest

from sdlc.adopt.source_tree import DEFAULT_SOURCE_TREE_GLOBS, effective_source_globs, is_source_path

pytestmark = pytest.mark.unit


def test_claude_paths_are_never_source() -> None:
    assert not is_source_path(".claude")
    assert not is_source_path(".claude/state/x.json")


def test_default_patterns_match_common_layouts() -> None:
    assert is_source_path("src/app.py")
    assert is_source_path("lib/utils.py")
    assert is_source_path("packages/api/main.py")
    assert is_source_path("pom.xml")


def test_legacy_globs_union_extends_source_tree() -> None:
    globs = effective_source_globs(("custom-src/**",))
    assert "custom-src/**" in globs
    assert DEFAULT_SOURCE_TREE_GLOBS[0] in globs
    assert is_source_path("custom-src/foo.py", ("custom-src/**",))

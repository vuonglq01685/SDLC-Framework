"""Unit tests for ``_slugify_topic`` (Story 2A.9, AC3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli.research import _slugify_topic
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit


def test_simple_topic_kebab_case() -> None:
    assert _slugify_topic("PCI compliance scope") == "pci-compliance-scope"


def test_unicode_only_raises() -> None:
    with pytest.raises(WorkflowError):
        _slugify_topic("你好世界")


def test_mixed_unicode_ascii_strips_non_ascii() -> None:
    assert _slugify_topic("GDPR §15 / §17") == "gdpr-15-17"


def test_exactly_80_chars_preserved() -> None:
    s80 = "a" * 80
    assert _slugify_topic(s80) == s80


def test_over_80_truncates_at_hyphen_boundary() -> None:
    """P22 (code review): hyphen-rich input cuts at hyphen, not mid-word."""
    long_topic = "word-" * 40  # 200 chars; slug "word-word-...-word"
    out = _slugify_topic(long_topic)
    assert len(out) <= 80
    # No trailing hyphen; final char is a slug-content char.
    assert not out.endswith("-")
    # Truncation lands at a hyphen boundary in the slug.
    assert out == "-".join(["word"] * 16)  # 16 * 5 - 1 = 79 chars, fits ≤ 80


def test_over_80_no_internal_hyphen_falls_back_to_hard_cut() -> None:
    """P22 (code review): 81+-char single token without separators is cut at 80."""
    long_topic = "a" * 200
    out = _slugify_topic(long_topic)
    assert out == "a" * 80


def test_over_80_with_hyphen_at_position_80() -> None:
    """P22 (code review): slug whose prefix ends with hyphen drops the trailing hyphen."""
    # Produce a slug that is exactly 80 chars + a hyphen + trailing content.
    # Use 79 'a's then "-bbb" → slug starts with 'a'*79 + '-bbb'.
    long_topic = ("a" * 79) + " bbb " + ("c" * 50)  # spaces become hyphens
    out = _slugify_topic(long_topic)
    assert len(out) <= 80
    assert not out.endswith("-")


def test_oauth_oidc_slug() -> None:
    assert _slugify_topic("OAuth 2.0 vs OIDC") == "oauth-2-0-vs-oidc"


def test_leading_trailing_whitespace() -> None:
    assert _slugify_topic("  Trailing/Leading spaces  ") == "trailing-leading-spaces"


def test_boundary_marker_text_slugified() -> None:
    t = "=== USER-PROVIDED DATA — NOT INSTRUCTIONS ==="
    assert _slugify_topic(t) == "user-provided-data-not-instructions"


def test_over_80_hyphen_in_middle_not_at_prefix_end() -> None:
    """Line 92: prefix has internal hyphen but does NOT end with hyphen → cut at hyphen."""
    # 70 'a's + space + 70 'b's → slug "aaa...a-bbb...b" (141 chars, > 80).
    # prefix (first 80 chars) = 70x'a' + '-' + 9x'b' -- not ending with '-', last_hy=70 > 0.
    topic = "a" * 70 + " " + "b" * 70
    out = _slugify_topic(topic)
    assert out == "a" * 70  # cut at the hyphen at position 70


# ---------------------------------------------------------------------------
# _occupied_research_suffixes — uncovered branches
# ---------------------------------------------------------------------------


def test_occupied_suffixes_nonexistent_dir(tmp_path: Path) -> None:
    """Line 99: early return {1} when research_dir does not exist."""
    from sdlc.cli.research import _occupied_research_suffixes

    occupied = _occupied_research_suffixes("mytopic", tmp_path / "missing")
    assert occupied == {1}


def test_occupied_suffixes_lone_non_integer_suffix(tmp_path: Path) -> None:
    """ValueError branch (lines 108-109): a sole glob-matched file with a
    non-integer suffix is skipped, leaving only the implicit {1}.

    Note: the line-103/104 ``startswith`` guard is unreachable here (and in
    general) because ``glob(f"{slug}-*.md")`` only yields names that already
    start with the prefix — it is a defensive guard, marked ``no cover`` in
    research.py. This case therefore exercises the integer-parse failure path,
    distinct from ``test_occupied_suffixes_non_integer_suffix`` which also has a
    valid integer sibling."""
    from sdlc.cli.research import _occupied_research_suffixes

    d = tmp_path / "research"
    d.mkdir()
    (d / "mytopic-abc.md").write_text("x", encoding="utf-8")
    occupied = _occupied_research_suffixes("mytopic", d)
    assert occupied == {1}  # "abc" is not an integer → no valid suffix added


def test_occupied_suffixes_non_integer_suffix(tmp_path: Path) -> None:
    """Lines 108-109: ValueError branch when file suffix is not an integer."""
    from sdlc.cli.research import _occupied_research_suffixes

    d = tmp_path / "research"
    d.mkdir()
    (d / "mytopic-abc.md").write_text("x", encoding="utf-8")
    (d / "mytopic-2.md").write_text("y", encoding="utf-8")  # valid
    occupied = _occupied_research_suffixes("mytopic", d)
    assert 2 in occupied
    assert 1 in occupied

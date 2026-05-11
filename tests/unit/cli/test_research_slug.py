"""Unit tests for ``_slugify_topic`` (Story 2A.9, AC3)."""

from __future__ import annotations

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

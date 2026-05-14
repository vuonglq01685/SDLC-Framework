"""Story 2A.11 AC9 — string patterns in ``parsers`` match compiled regexes (Story 1.6)."""

from __future__ import annotations

import re

import pytest

from sdlc.errors import IdsError
from sdlc.ids.parsers import (
    EPIC_ID_PATTERN,
    EPIC_ID_REGEX,
    STORY_ID_PATTERN,
    STORY_ID_REGEX,
    parse_epic_id,
    parse_story_id,
)

pytestmark = pytest.mark.unit


def test_epic_pattern_matches_compiled_regex() -> None:
    assert EPIC_ID_REGEX.pattern == EPIC_ID_PATTERN


def test_story_pattern_matches_compiled_regex() -> None:
    assert STORY_ID_REGEX.pattern == STORY_ID_PATTERN


@pytest.mark.parametrize(
    "raw",
    [
        "epic-no-prefix",
        "EPIC-InvalidCase",
        "EPIC-foo-S01-bar",
        "EPIC-",
    ],
)
def test_epic_pattern_rejects_malformed(raw: str) -> None:
    assert EPIC_ID_REGEX.fullmatch(raw) is None


def test_permissive_wildcard_would_accept_malformed_epic_id() -> None:
    """AC9 anti-tautology receipt: a ``.*`` pattern would wrongly accept this input."""
    bad = "epic-no-prefix"
    assert re.fullmatch(r".*", bad) is not None
    assert EPIC_ID_REGEX.fullmatch(bad) is None


def test_parse_epic_id_round_trip_matches_pattern() -> None:
    raw = "EPIC-stripe-webhook"
    e = parse_epic_id(raw)
    assert e.raw == raw
    assert EPIC_ID_REGEX.fullmatch(raw) is not None


def test_parse_story_id_round_trip_matches_pattern() -> None:
    raw = "EPIC-stripe-webhook-S03-capture-payment"
    s = parse_story_id(raw)
    assert s.raw == raw
    assert STORY_ID_REGEX.fullmatch(raw) is not None


def test_story_pattern_rejects_missing_story_segment() -> None:
    with pytest.raises(IdsError) as exc_info:
        parse_story_id("EPIC-foo-S4-bar")
    assert exc_info.value.details.get("rule") == "invalid_story_shape"

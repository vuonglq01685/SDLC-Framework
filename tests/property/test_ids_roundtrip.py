from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sdlc.ids import (
    build_epic_id,
    build_story_id,
    build_task_id,
    parse_epic_id,
    parse_story_id,
    parse_task_id,
)

# Strategy: lowercase kebab-case slug segments ([a-z0-9]+ chunks joined by single dashes)
_slug_segment = st.from_regex(r"[a-z0-9]+", fullmatch=True)
_slug = st.lists(_slug_segment, min_size=1, max_size=5).map("-".join)
_num = st.integers(min_value=0, max_value=99)


@pytest.mark.property
@given(epic_slug=_slug)
@settings(max_examples=200)
def test_epic_id_roundtrip(epic_slug: str) -> None:
    built = build_epic_id(epic_slug)
    parsed = parse_epic_id(built.raw)
    assert parsed == built
    assert parsed.raw == built.raw


@pytest.mark.property
@given(epic_slug=_slug, story_num=_num, story_slug=_slug)
@settings(max_examples=200)
def test_story_id_roundtrip(epic_slug: str, story_num: int, story_slug: str) -> None:
    built = build_story_id(epic_slug, story_num, story_slug)
    parsed = parse_story_id(built.raw)
    assert parsed == built
    assert parsed.raw == built.raw


@pytest.mark.property
@given(epic_slug=_slug, story_num=_num, story_slug=_slug, task_num=_num, task_slug=_slug)
@settings(max_examples=200)
def test_task_id_roundtrip(
    epic_slug: str,
    story_num: int,
    story_slug: str,
    task_num: int,
    task_slug: str,
) -> None:
    built = build_task_id(epic_slug, story_num, story_slug, task_num, task_slug)
    parsed = parse_task_id(built.raw)
    assert parsed == built
    assert parsed.raw == built.raw

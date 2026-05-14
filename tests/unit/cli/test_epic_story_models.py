"""Unit tests for ``_EpicEntry`` / ``_StoryEntry`` (Story 2A.11, Task 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.cli._epic_story_models import _EpicEntry, _StoryEntry, serialize_entry

pytestmark = pytest.mark.unit


def _epic_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "id": "EPIC-test-epic",
        "label": "Test epic",
        "priority": "P1",
        "dependencies": (),
        "ordering": 0,
        "acceptance_criteria": ("First criterion",),
        "drafted_at": "2026-01-15T12:00:00.000Z",
        "drafted_by_specialist": "epic-generator",
    }
    base.update(overrides)
    return base


def _story_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "id": "EPIC-stripe-webhook-S01-capture-intent",
        "epic_id": "EPIC-stripe-webhook",
        "seq": 1,
        "label": "Capture intent",
        "as_a": "PM",
        "i_want": "stories",
        "so_that": "we ship",
        "given_when_then": ("Given x\nWhen y\nThen z",),
        "dependencies": (),
        "drafted_at": "2026-01-15T12:00:00.000Z",
        "drafted_by_specialist": "story-writer",
    }
    base.update(overrides)
    return base


def test_epic_entry_happy_path() -> None:
    e = _EpicEntry.model_validate(_epic_kwargs())
    assert e.id == "EPIC-test-epic"


def test_epic_entry_rejects_invalid_id_regex() -> None:
    with pytest.raises(ValidationError):
        _EpicEntry.model_validate(_epic_kwargs(id="not-an-epic"))


def test_epic_entry_rejects_invalid_priority() -> None:
    with pytest.raises(ValidationError):
        _EpicEntry.model_validate(_epic_kwargs(priority="P9"))


def test_epic_entry_rejects_empty_acceptance_criteria() -> None:
    with pytest.raises(ValidationError):
        _EpicEntry.model_validate(_epic_kwargs(acceptance_criteria=()))


def test_epic_entry_rejects_extra_fields() -> None:
    d = _epic_kwargs()
    d["extra"] = 1
    with pytest.raises(ValidationError):
        _EpicEntry.model_validate(d)


def test_story_entry_happy_path() -> None:
    s = _StoryEntry.model_validate(_story_kwargs())
    assert s.epic_id == "EPIC-stripe-webhook"


def test_story_entry_rejects_id_not_starting_with_epic_id() -> None:
    with pytest.raises(ValidationError):
        _StoryEntry.model_validate(
            _story_kwargs(id="EPIC-other-S01-x", epic_id="EPIC-stripe-webhook"),
        )


def test_story_entry_rejects_seq_mismatch_with_id() -> None:
    with pytest.raises(ValidationError):
        _StoryEntry.model_validate(
            _story_kwargs(id="EPIC-stripe-webhook-S02-x", seq=1),
        )


def test_story_entry_rejects_seq_below_one() -> None:
    with pytest.raises(ValidationError):
        _StoryEntry.model_validate(_story_kwargs(seq=0, id="EPIC-stripe-webhook-S01-x"))


def test_story_entry_rejects_empty_given_when_then() -> None:
    with pytest.raises(ValidationError):
        _StoryEntry.model_validate(_story_kwargs(given_when_then=()))


def test_serialize_entry_byte_stable_round_trip() -> None:
    e = _EpicEntry.model_validate(_epic_kwargs())
    a = serialize_entry(e)
    b = serialize_entry(_EpicEntry.model_validate_json(a))
    assert a == b

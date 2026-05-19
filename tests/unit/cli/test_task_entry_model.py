"""Unit tests for ``_TaskEntry`` StrictModel (Story 2A.16, AC4, Task 2.1; extended 2A.17, AC8)."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit

_VALID_STORY_ID = "EPIC-foo-S01-bar"
_VALID_TASK_ID = "EPIC-foo-S01-bar-T01-design-data-model"


def _make_valid_record(
    *,
    task_id: str = _VALID_TASK_ID,
    story_id: str = _VALID_STORY_ID,
    label: str = "Design the data model.",
    stage: str = "pending",
    dependencies: list[str] | None = None,
    review_verdict: str | None = None,
    review_notes: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": task_id,
        "story_id": story_id,
        "label": label,
        "stage": stage,
        "dependencies": dependencies if dependencies is not None else [],
    }
    if review_verdict is not None:
        record["review_verdict"] = review_verdict
    if review_notes is not None:
        record["review_notes"] = review_notes
    return record


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------


def test_task_entry_valid_record_parses_cleanly() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    assert entry.id == _VALID_TASK_ID
    assert entry.story_id == _VALID_STORY_ID
    assert entry.label == "Design the data model."
    assert entry.stage == "pending"
    assert entry.dependencies == []


def test_task_entry_with_dependencies_parses_cleanly() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    dep_id = "EPIC-foo-S01-bar-T01-design-data-model"
    task_id = "EPIC-foo-S01-bar-T02-implement-write-path"
    entry = _TaskEntry(**_make_valid_record(task_id=task_id, dependencies=[dep_id]))  # type: ignore[arg-type]
    assert entry.dependencies == [dep_id]


def test_task_entry_stage_defaults_to_pending() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    del record["stage"]
    entry = _TaskEntry(**record)  # type: ignore[arg-type]
    assert entry.stage == "pending"


def test_task_entry_dependencies_defaults_to_empty() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    del record["dependencies"]
    entry = _TaskEntry(**record)  # type: ignore[arg-type]
    assert entry.dependencies == []


# ---------------------------------------------------------------------------
# Missing required fields → ValidationError
# ---------------------------------------------------------------------------


def test_task_entry_missing_id_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    del record["id"]
    with pytest.raises(ValidationError):
        _TaskEntry(**record)  # type: ignore[arg-type]


def test_task_entry_missing_story_id_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    del record["story_id"]
    with pytest.raises(ValidationError):
        _TaskEntry(**record)  # type: ignore[arg-type]


def test_task_entry_missing_label_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    del record["label"]
    with pytest.raises(ValidationError):
        _TaskEntry(**record)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Regex validation
# ---------------------------------------------------------------------------


def test_task_entry_id_not_matching_task_id_regex_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError, match="TASK_ID_REGEX"):
        _TaskEntry(**_make_valid_record(task_id="not-a-valid-task-id"))  # type: ignore[arg-type]


def test_task_entry_id_is_story_id_not_task_id_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    # A story ID (no T-segment) should fail task regex
    with pytest.raises(ValidationError, match="TASK_ID_REGEX"):
        _TaskEntry(**_make_valid_record(task_id="EPIC-foo-S01-bar"))  # type: ignore[arg-type]


def test_task_entry_story_id_not_matching_story_id_regex_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError, match="STORY_ID_REGEX"):
        _TaskEntry(**_make_valid_record(story_id="not-a-valid-story-id"))  # type: ignore[arg-type]


def test_task_entry_story_id_is_epic_id_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    # An epic ID (no S-segment) should fail story regex
    with pytest.raises(ValidationError, match="STORY_ID_REGEX"):
        _TaskEntry(**_make_valid_record(story_id="EPIC-foo"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stage constraint
# ---------------------------------------------------------------------------


def test_task_entry_stage_unknown_value_raises_validation_error() -> None:
    """stage must be one of the 5 known values; arbitrary strings are rejected (AC8)."""
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError):
        _TaskEntry(**_make_valid_record(stage="running"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Dependencies validation
# ---------------------------------------------------------------------------


def test_task_entry_dependencies_non_list_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    record = _make_valid_record()
    record["dependencies"] = "not-a-list"
    with pytest.raises(ValidationError):
        _TaskEntry(**record)  # type: ignore[arg-type]


def test_task_entry_dependency_id_not_matching_task_id_regex_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError, match="TASK_ID_REGEX"):
        _TaskEntry(**_make_valid_record(dependencies=["not-a-task-id"]))  # type: ignore[arg-type]


def test_task_entry_dependency_id_is_story_id_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    # A story ID should not be accepted as a dependency (needs -T segment)
    with pytest.raises(ValidationError, match="TASK_ID_REGEX"):
        _TaskEntry(**_make_valid_record(dependencies=["EPIC-foo-S01-bar"]))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# serialize_task_entry helper
# ---------------------------------------------------------------------------


def test_serialize_task_entry_produces_valid_json() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    text = serialize_task_entry(entry)
    parsed = json.loads(text)
    assert parsed["id"] == _VALID_TASK_ID
    assert parsed["story_id"] == _VALID_STORY_ID
    assert parsed["stage"] == "pending"
    assert parsed["dependencies"] == []
    assert text.endswith("\n")


def test_serialize_task_entry_is_deterministic() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    assert serialize_task_entry(entry) == serialize_task_entry(entry)


# ---------------------------------------------------------------------------
# Story 2A.17 AC8 — 5-state Literal + review fields
# ---------------------------------------------------------------------------


def test_task_entry_stage_accepts_all_five_values() -> None:
    """stage Literal widened to 5-state machine (AC8)."""
    from sdlc.cli._epic_story_models import _TaskEntry

    for stage in ("pending", "write-tests", "write-code", "review", "done"):
        entry = _TaskEntry(**_make_valid_record(stage=stage))  # type: ignore[arg-type]
        assert entry.stage == stage


# Unknown-stage rejection is covered by
# ``test_task_entry_stage_unknown_value_raises_validation_error`` above.


def test_task_entry_review_verdict_defaults_to_none() -> None:
    """review_verdict defaults to None when omitted (AC8)."""
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    assert entry.review_verdict is None


def test_task_entry_review_notes_defaults_to_none() -> None:
    """review_notes defaults to None when omitted (AC8)."""
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    assert entry.review_notes is None


def test_task_entry_review_verdict_approved_accepted() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record(review_verdict="approved"))  # type: ignore[arg-type]
    assert entry.review_verdict == "approved"


def test_task_entry_review_verdict_rejected_accepted() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record(review_verdict="rejected"))  # type: ignore[arg-type]
    assert entry.review_verdict == "rejected"


def test_task_entry_review_verdict_invalid_value_raises_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError):
        _TaskEntry(**_make_valid_record(review_verdict="unknown"))  # type: ignore[arg-type]


def test_task_entry_review_notes_accepts_string() -> None:
    from sdlc.cli._epic_story_models import _TaskEntry

    entry = _TaskEntry(**_make_valid_record(review_notes="looks good"))  # type: ignore[arg-type]
    assert entry.review_notes == "looks good"


def test_serialize_task_entry_includes_review_fields_when_set() -> None:
    """serialize_task_entry includes review_verdict and review_notes in JSON (AC8/D1)."""
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(  # type: ignore[call-arg]
        **_make_valid_record(
            stage="review",
            review_verdict="approved",
            review_notes="LGTM",
        )
    )
    text = serialize_task_entry(entry)
    parsed = json.loads(text)
    assert parsed["stage"] == "review"
    assert parsed["review_verdict"] == "approved"
    assert parsed["review_notes"] == "LGTM"


def test_serialize_task_entry_review_fields_null_when_unset() -> None:
    """Null review fields are serialized as null (AC8/D1 — key set grows on first advance)."""
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    entry = _TaskEntry(**_make_valid_record())  # type: ignore[arg-type]
    text = serialize_task_entry(entry)
    parsed = json.loads(text)
    assert parsed["review_verdict"] is None
    assert parsed["review_notes"] is None


def test_serialize_task_entry_round_trips_extended_shape() -> None:
    """Extended _TaskEntry round-trips through serialize → parse correctly (AC8)."""
    from sdlc.cli._epic_story_models import _TaskEntry, serialize_task_entry

    original = _TaskEntry(  # type: ignore[call-arg]
        **_make_valid_record(
            stage="done",
            review_verdict="approved",
            review_notes="All checks passed.",
        )
    )
    text = serialize_task_entry(original)
    parsed = json.loads(text)
    restored = _TaskEntry(**parsed)  # type: ignore[arg-type]
    assert restored.stage == "done"
    assert restored.review_verdict == "approved"
    assert restored.review_notes == "All checks passed."

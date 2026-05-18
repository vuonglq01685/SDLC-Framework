"""Unit tests for ``_TaskEntry`` StrictModel (Story 2A.16, AC4, Task 2.1)."""

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
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": task_id,
        "story_id": story_id,
        "label": label,
        "stage": stage,
        "dependencies": dependencies if dependencies is not None else [],
    }
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


def test_task_entry_stage_not_pending_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError):
        _TaskEntry(**_make_valid_record(stage="done"))  # type: ignore[arg-type]


def test_task_entry_stage_in_progress_raises_validation_error() -> None:
    from pydantic import ValidationError

    from sdlc.cli._epic_story_models import _TaskEntry

    with pytest.raises(ValidationError):
        _TaskEntry(**_make_valid_record(stage="in-progress"))  # type: ignore[arg-type]


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

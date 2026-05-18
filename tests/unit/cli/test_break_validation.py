"""Unit tests for ``_validate_task_batch`` + ``_check_dep_dag`` (Story 2A.16, AC4, Task 2.4)."""

from __future__ import annotations

import pytest

from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit

_STORY_ID = "EPIC-foo-S01-bar"
_T01 = "EPIC-foo-S01-bar-T01-design-data-model"
_T02 = "EPIC-foo-S01-bar-T02-implement-write-path"
_T03 = "EPIC-foo-S01-bar-T03-implement-read-path"


def _make_entry(
    task_id: str,
    *,
    story_id: str = _STORY_ID,
    label: str = "A task.",
    dependencies: list[str] | None = None,
) -> object:
    from sdlc.cli._epic_story_models import _TaskEntry

    return _TaskEntry(
        id=task_id,
        story_id=story_id,
        label=label,
        stage="pending",
        dependencies=dependencies if dependencies is not None else [],
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_task_batch_single_task_ok() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    records = [_make_entry(_T01)]
    _validate_task_batch(records, request_story_id=_STORY_ID)  # no exception


def test_validate_task_batch_chained_deps_ok() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    records = [
        _make_entry(_T01),
        _make_entry(_T02, dependencies=[_T01]),
        _make_entry(_T03, dependencies=[_T01]),
    ]
    _validate_task_batch(records, request_story_id=_STORY_ID)  # no exception


# ---------------------------------------------------------------------------
# story_id cross-validation
# ---------------------------------------------------------------------------


def test_validate_task_batch_wrong_story_id_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    other_story = "EPIC-foo-S02-other"
    task_with_wrong = _make_entry(
        "EPIC-foo-S02-other-T01-bad",
        story_id=other_story,
    )
    with pytest.raises(WorkflowError, match="wrong story_id"):
        _validate_task_batch([task_with_wrong], request_story_id=_STORY_ID)


def test_validate_task_batch_id_story_prefix_mismatch_raises() -> None:
    """The story-id encoded in the task id must match the request story.

    A record whose ``story_id`` field equals the request but whose ``id``
    encodes a different story must be rejected (lineage cross-check).
    """
    from sdlc.cli._break_pipeline import _validate_task_batch

    # story_id field matches the request, but the id encodes EPIC-foo-S02-other
    foreign_id_task = _make_entry(
        "EPIC-foo-S02-other-T01-foreign",
        story_id=_STORY_ID,
    )
    with pytest.raises(WorkflowError, match="id encodes story"):
        _validate_task_batch([foreign_id_task], request_story_id=_STORY_ID)


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------


def test_validate_task_batch_duplicate_id_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    records = [_make_entry(_T01), _make_entry(_T01)]
    with pytest.raises(WorkflowError, match="duplicate task id"):
        _validate_task_batch(records, request_story_id=_STORY_ID)


# ---------------------------------------------------------------------------
# Dependency references
# ---------------------------------------------------------------------------


def test_validate_task_batch_dep_not_in_batch_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    orphan_dep = "EPIC-foo-S01-bar-T99-nonexistent"
    records = [_make_entry(_T01, dependencies=[orphan_dep])]
    with pytest.raises(WorkflowError, match=r"dependency.*not in this batch"):
        _validate_task_batch(records, request_story_id=_STORY_ID)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def test_validate_task_batch_cycle_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    records = [
        _make_entry(_T01, dependencies=[_T02]),
        _make_entry(_T02, dependencies=[_T01]),
    ]
    with pytest.raises(WorkflowError, match="cycle"):
        _validate_task_batch(records, request_story_id=_STORY_ID)


def test_validate_task_batch_three_node_cycle_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    records = [
        _make_entry(_T01, dependencies=[_T03]),
        _make_entry(_T02, dependencies=[_T01]),
        _make_entry(_T03, dependencies=[_T02]),
    ]
    with pytest.raises(WorkflowError, match="cycle"):
        _validate_task_batch(records, request_story_id=_STORY_ID)


# ---------------------------------------------------------------------------
# Seq contiguity
# ---------------------------------------------------------------------------


def test_validate_task_batch_seq_gap_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    # T01 + T03 (skip T02) = gap
    t01 = _make_entry("EPIC-foo-S01-bar-T01-first")
    t03 = _make_entry("EPIC-foo-S01-bar-T03-third")
    with pytest.raises(WorkflowError, match="seq gap"):
        _validate_task_batch([t01, t03], request_story_id=_STORY_ID)


def test_validate_task_batch_seq_not_starting_at_01_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    t02 = _make_entry("EPIC-foo-S01-bar-T02-second")
    with pytest.raises(WorkflowError, match="seq gap"):
        _validate_task_batch([t02], request_story_id=_STORY_ID)


def test_validate_task_batch_empty_batch_raises() -> None:
    from sdlc.cli._break_pipeline import _validate_task_batch

    with pytest.raises(WorkflowError, match="empty"):
        _validate_task_batch([], request_story_id=_STORY_ID)

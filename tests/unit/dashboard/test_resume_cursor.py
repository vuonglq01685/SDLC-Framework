"""Unit tests for ``find_current_cursor`` (Story 5.18 D1/D3).

``resume_token.cursor`` (epic_id/story_id/task_id/stage) is derived from the
SAME real Epic->Story->Task artifact tree ``build_backlog_tree`` (Story 5.15)
already reads -- ``state.json`` does not project the hierarchy (D1 gap,
verified in both stories) -- but retains the task's RAW 5-value workflow
``stage`` (pending/write-tests/write-code/review/done) instead of the
3-value display pill ``build_backlog_tree`` derives for the backlog tree.

Fixture JSON is built through the REAL writer models (2A.11) so this test
exercises the actual on-disk byte shape, not a hand-rolled approximation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.cli._epic_story_models import (
    _EpicEntry,
    _StoryEntry,
    _TaskEntry,
    serialize_entry,
    serialize_task_entry,
)
from sdlc.dashboard.routes.backlog import find_current_cursor

pytestmark = pytest.mark.unit

_DRAFTED_AT = "2026-07-01T00:00:00.000Z"
_EPICS_DIR = "01-Requirement/04-Epics"
_STORIES_DIR = "01-Requirement/05-Stories"
_TASKS_DIR = "03-Implementation/tasks"


def _write_epic(root: Path, *, id_: str, label: str, ordering: int = 0) -> None:
    entry = _EpicEntry(
        id=id_,
        label=label,
        priority="P1",
        ordering=ordering,
        acceptance_criteria=("Criterion 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="epic-generator",
    )
    path = root / _EPICS_DIR / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_story(root: Path, *, id_: str, epic_id: str, seq: int, label: str) -> None:
    entry = _StoryEntry(
        id=id_,
        epic_id=epic_id,
        seq=seq,
        label=label,
        as_a="a user",
        i_want="a thing",
        so_that="value",
        given_when_then=("Given/When/Then 1",),
        drafted_at=_DRAFTED_AT,
        drafted_by_specialist="story-writer",
    )
    path = root / _STORIES_DIR / epic_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entry(entry), encoding="utf-8")


def _write_task(root: Path, *, id_: str, story_id: str, label: str, stage: str = "pending") -> None:
    entry = _TaskEntry(id=id_, story_id=story_id, label=label, stage=stage)
    path = root / _TASKS_DIR / story_id / f"{id_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_task_entry(entry), encoding="utf-8")


def test_no_epics_returns_none(tmp_path: Path) -> None:
    assert find_current_cursor(tmp_path) is None


def test_first_non_done_task_in_canonical_order(tmp_path: Path) -> None:
    _write_epic(tmp_path, id_="EPIC-stripe-webhook", label="Stripe webhook", ordering=0)
    _write_story(
        tmp_path,
        id_="EPIC-stripe-webhook-S01-setup",
        epic_id="EPIC-stripe-webhook",
        seq=1,
        label="Setup",
    )
    _write_task(
        tmp_path,
        id_="EPIC-stripe-webhook-S01-setup-T01-init",
        story_id="EPIC-stripe-webhook-S01-setup",
        label="Init",
        stage="done",
    )
    _write_task(
        tmp_path,
        id_="EPIC-stripe-webhook-S01-setup-T02-wire",
        story_id="EPIC-stripe-webhook-S01-setup",
        label="Wire",
        stage="write-tests",
    )
    cursor = find_current_cursor(tmp_path)
    assert cursor == {
        "epic_id": "EPIC-stripe-webhook",
        "story_id": "EPIC-stripe-webhook-S01-setup",
        "task_id": "EPIC-stripe-webhook-S01-setup-T02-wire",
        "stage": "write-tests",
    }


def test_all_tasks_done_returns_none(tmp_path: Path) -> None:
    _write_epic(tmp_path, id_="EPIC-x", label="X")
    _write_story(tmp_path, id_="EPIC-x-S01-a", epic_id="EPIC-x", seq=1, label="A")
    _write_task(
        tmp_path, id_="EPIC-x-S01-a-T01-b", story_id="EPIC-x-S01-a", label="B", stage="done"
    )
    assert find_current_cursor(tmp_path) is None


def test_malformed_epic_id_skipped(tmp_path: Path) -> None:
    """D5 tolerance: a story/task under an epic id that fails canonical parsing is
    skipped, never raised (mirrors build_backlog_tree's malformed-id handling)."""
    epics_dir = tmp_path / _EPICS_DIR
    epics_dir.mkdir(parents=True)
    (epics_dir / "not-canonical.json").write_text(
        '{"schema_version":1,"id":"not-canonical","label":"bad","priority":"P1",'
        '"ordering":0,"acceptance_criteria":["x"],"drafted_at":"2026-07-01T00:00:00.000Z",'
        '"drafted_by_specialist":"x"}',
        encoding="utf-8",
    )
    assert find_current_cursor(tmp_path) is None


def test_non_string_stage_treated_as_pending(tmp_path: Path) -> None:
    """A malformed (non-string) stage on-disk value is coerced defensively, never
    raised and never fabricated as a lie -- treated as the safe 'pending' default."""
    import json

    _write_epic(tmp_path, id_="EPIC-x", label="X")
    _write_story(tmp_path, id_="EPIC-x-S01-a", epic_id="EPIC-x", seq=1, label="A")
    _write_task(tmp_path, id_="EPIC-x-S01-a-T01-b", story_id="EPIC-x-S01-a", label="B")
    task_path = tmp_path / _TASKS_DIR / "EPIC-x-S01-a" / "EPIC-x-S01-a-T01-b.json"
    data = json.loads(task_path.read_text(encoding="utf-8"))
    data["stage"] = 123
    task_path.write_text(json.dumps(data), encoding="utf-8")
    cursor = find_current_cursor(tmp_path)
    assert cursor is not None
    assert cursor["stage"] == "pending"

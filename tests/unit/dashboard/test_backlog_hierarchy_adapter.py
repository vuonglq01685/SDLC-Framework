"""Golden-fixture + contract tests for the real hierarchy nesting adapter (Story 5.15 Task 1).

Story 2A.11 writes the real Epic->Story->Task hierarchy as canonical-id-keyed
JSON files under ``01-Requirement/04-Epics/`` + ``01-Requirement/05-Stories/<epic-id>/``
+ ``03-Implementation/tasks/<story-dir>/`` (D1: the projection reserves
story-/task- folding "for later stories", so state.json's own ``stories``/
``tasks`` stay empty -- this is NOT a re-parse of the wire ``/state.json``
file). ``build_backlog_tree`` is a PURE function: it groups each STORY under
its EPIC and each TASK under its STORY by parsing the canonical id (D2),
never by trusting directory names, and emits the exact
``{currentTaskId, epics:[...]}`` shape the FROZEN 5.10 ``renderBacklogTree``
already consumes.

Fixture JSON is built through the REAL writer models
(``sdlc.cli._epic_story_models``) so this test exercises the actual on-disk
byte shape 2A.11 produces, not a hand-rolled approximation.
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
from sdlc.dashboard.routes.backlog import build_backlog_tree
from sdlc.ids.parsers import EPIC_ID_REGEX, STORY_ID_REGEX, TASK_ID_REGEX

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


def _all_ids(tree: dict) -> set[str]:
    ids: set[str] = set()
    for epic in tree["epics"]:
        ids.add(epic["id"])
        for story in epic["stories"]:
            ids.add(story["id"])
            for task in story["tasks"]:
                ids.add(task["id"])
    return ids


class TestEmptyAndMalformedInput:
    def test_no_artifact_tree_returns_empty_epics_and_no_current_task(self, tmp_path: Path) -> None:
        tree = build_backlog_tree(tmp_path)
        assert tree == {"currentTaskId": "", "epics": []}

    def test_malformed_epic_json_is_skipped_not_crashed(self, tmp_path: Path) -> None:
        bad = tmp_path / _EPICS_DIR / "EPIC-broken.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("}{not json{", encoding="utf-8")
        tree = build_backlog_tree(tmp_path)
        assert tree["epics"] == []

    def test_epic_with_non_canonical_id_field_is_skipped(self, tmp_path: Path) -> None:
        """A directory-name/id mismatch or malformed id must never render 'undefined' (D5)."""
        path = tmp_path / _EPICS_DIR / "EPIC-weird.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id": "not-a-canonical-id", "label": "x"}', encoding="utf-8")
        tree = build_backlog_tree(tmp_path)
        assert tree["epics"] == []

    def test_non_int_ordering_does_not_crash_the_whole_endpoint(self, tmp_path: Path) -> None:
        """Review P-1: a malformed `ordering` (null/str) must not TypeError-crash
        the epic sort and 500 the entire tree -- it sorts as 0, never raises."""
        epics_dir = tmp_path / _EPICS_DIR
        epics_dir.mkdir(parents=True, exist_ok=True)
        # A null `ordering` compared against another file's int ordering in the
        # sort key raised `TypeError: '<' not supported between NoneType and int`
        # before the fix -- taking down the whole /api/backlog tree.
        (epics_dir / "EPIC-alpha.json").write_text(
            '{"id": "EPIC-alpha", "label": "Alpha", "ordering": null}', encoding="utf-8"
        )
        (epics_dir / "EPIC-beta.json").write_text(
            '{"id": "EPIC-beta", "label": "Beta", "ordering": 5}', encoding="utf-8"
        )
        tree = build_backlog_tree(tmp_path)  # must not raise
        assert {e["id"] for e in tree["epics"]} == {"EPIC-alpha", "EPIC-beta"}
        # null-ordering (coerced to 0) sorts before the int-5 epic.
        assert [e["id"] for e in tree["epics"]] == ["EPIC-alpha", "EPIC-beta"]


class TestGoldenFixtureRoundTrip:
    """RED (pre-adapter): a well-formed hierarchy fails to round-trip 1:1.
    GREEN: every real id appears in the derived nest exactly once, correctly
    nested -- no dropped/added/duplicated/reordered node."""

    def test_well_formed_hierarchy_round_trips_every_id_exactly_once(self, tmp_path: Path) -> None:
        _write_epic(
            tmp_path, id_="EPIC-stripe-webhook", label="Stripe webhook pipeline", ordering=0
        )
        _write_story(
            tmp_path,
            id_="EPIC-stripe-webhook-S01-idempotency",
            epic_id="EPIC-stripe-webhook",
            seq=1,
            label="Idempotency handling",
        )
        _write_story(
            tmp_path,
            id_="EPIC-stripe-webhook-S02-signature",
            epic_id="EPIC-stripe-webhook",
            seq=2,
            label="Signature verification",
        )
        _write_task(
            tmp_path,
            id_="EPIC-stripe-webhook-S01-idempotency-T01-redis-key",
            story_id="EPIC-stripe-webhook-S01-idempotency",
            label="Redis key design",
            stage="done",
        )
        _write_task(
            tmp_path,
            id_="EPIC-stripe-webhook-S01-idempotency-T02-handler",
            story_id="EPIC-stripe-webhook-S01-idempotency",
            label="Handler integration",
            stage="write-code",
        )

        tree = build_backlog_tree(tmp_path)

        expected_ids = {
            "EPIC-stripe-webhook",
            "EPIC-stripe-webhook-S01-idempotency",
            "EPIC-stripe-webhook-S02-signature",
            "EPIC-stripe-webhook-S01-idempotency-T01-redis-key",
            "EPIC-stripe-webhook-S01-idempotency-T02-handler",
        }
        assert _all_ids(tree) == expected_ids, "no dropped/added/duplicated node"

        epic = tree["epics"][0]
        assert epic["id"] == "EPIC-stripe-webhook"
        assert epic["kind"] == "EPIC"
        assert [s["id"] for s in epic["stories"]] == [
            "EPIC-stripe-webhook-S01-idempotency",
            "EPIC-stripe-webhook-S02-signature",
        ], "stories must be in seq order, not reordered"

        story1 = epic["stories"][0]
        assert story1["kind"] == "STORY"
        assert [t["id"] for t in story1["tasks"]] == [
            "EPIC-stripe-webhook-S01-idempotency-T01-redis-key",
            "EPIC-stripe-webhook-S01-idempotency-T02-handler",
        ], "tasks must be in task-num order, not reordered"

        story2 = epic["stories"][1]
        assert story2["tasks"] == []

    def test_multiple_epics_preserve_ordering_field(self, tmp_path: Path) -> None:
        _write_epic(tmp_path, id_="EPIC-second", label="Second", ordering=1)
        _write_epic(tmp_path, id_="EPIC-first", label="First", ordering=0)
        tree = build_backlog_tree(tmp_path)
        assert [e["id"] for e in tree["epics"]] == ["EPIC-first", "EPIC-second"]


class TestOrphanTolerance:
    def test_orphaned_task_without_matching_story_is_dropped_not_crashed(
        self, tmp_path: Path
    ) -> None:
        _write_epic(tmp_path, id_="EPIC-stripe-webhook", label="Stripe webhook pipeline")
        _write_story(
            tmp_path,
            id_="EPIC-stripe-webhook-S01-idempotency",
            epic_id="EPIC-stripe-webhook",
            seq=1,
            label="Idempotency handling",
        )
        # Orphan: task references a story id that was never written as a story file.
        _write_task(
            tmp_path,
            id_="EPIC-stripe-webhook-S99-ghost-T01-orphan",
            story_id="EPIC-stripe-webhook-S99-ghost",
            label="Orphan task",
        )
        tree = build_backlog_tree(tmp_path)  # must not raise
        assert "EPIC-stripe-webhook-S99-ghost-T01-orphan" not in _all_ids(tree)
        assert tree["epics"][0]["stories"][0]["tasks"] == []

    def test_orphaned_story_under_a_never_written_epic_is_unreachable(self, tmp_path: Path) -> None:
        # No EPIC-ghost-*.json written -> the story directory is never visited.
        _write_story(
            tmp_path,
            id_="EPIC-ghost-S01-nowhere",
            epic_id="EPIC-ghost",
            seq=1,
            label="Story with no epic",
        )
        tree = build_backlog_tree(tmp_path)
        assert tree["epics"] == []


class TestCanonicalIdRegexSource:
    def test_every_rendered_id_matches_the_shared_story_1_6_regex(self, tmp_path: Path) -> None:
        """Task 3: ids must validate against the SHARED Story 1.6 regex, not a copy."""
        _write_epic(tmp_path, id_="EPIC-stripe-webhook", label="Stripe webhook pipeline")
        _write_story(
            tmp_path,
            id_="EPIC-stripe-webhook-S04-idempotency",
            epic_id="EPIC-stripe-webhook",
            seq=4,
            label="Idempotency handling",
        )
        _write_task(
            tmp_path,
            id_="EPIC-stripe-webhook-S04-idempotency-T01-redis-key",
            story_id="EPIC-stripe-webhook-S04-idempotency",
            label="Redis key design",
        )
        tree = build_backlog_tree(tmp_path)
        epic = tree["epics"][0]
        assert EPIC_ID_REGEX.match(epic["id"])
        story = epic["stories"][0]
        assert STORY_ID_REGEX.match(story["id"])
        task = story["tasks"][0]
        assert TASK_ID_REGEX.match(task["id"])


class TestStatusDerivationAndCounts:
    def test_task_stage_maps_onto_the_pill_status_vocabulary(self, tmp_path: Path) -> None:
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-y", epic_id="EPIC-x", seq=1, label="Y")
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T01-a", story_id="EPIC-x-S01-y", label="A", stage="done"
        )
        _write_task(
            tmp_path,
            id_="EPIC-x-S01-y-T02-b",
            story_id="EPIC-x-S01-y",
            label="B",
            stage="write-tests",
        )
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T03-c", story_id="EPIC-x-S01-y", label="C", stage="pending"
        )
        tree = build_backlog_tree(tmp_path)
        tasks = {t["id"]: t["status"] for t in tree["epics"][0]["stories"][0]["tasks"]}
        assert tasks["EPIC-x-S01-y-T01-a"] == "done"
        assert tasks["EPIC-x-S01-y-T02-b"] == "in-progress"
        assert tasks["EPIC-x-S01-y-T03-c"] == "pending"

    def test_story_with_started_but_zero_done_tasks_is_in_progress_not_pending(
        self, tmp_path: Path
    ) -> None:
        """Review P-2: a mid-flight story (a task started, none done) must derive
        status 'in-progress', not 'pending' -- else the story header pill would
        contradict its own visible in-progress child task pill."""
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-y", epic_id="EPIC-x", seq=1, label="Y")
        _write_task(
            tmp_path,
            id_="EPIC-x-S01-y-T01-a",
            story_id="EPIC-x-S01-y",
            label="A",
            stage="write-code",
        )
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T02-b", story_id="EPIC-x-S01-y", label="B", stage="pending"
        )
        tree = build_backlog_tree(tmp_path)
        assert tree["epics"][0]["stories"][0]["status"] == "in-progress"

    def test_story_with_all_pending_tasks_is_pending(self, tmp_path: Path) -> None:
        """Review P-2 boundary: no task started -> the story is genuinely pending."""
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-y", epic_id="EPIC-x", seq=1, label="Y")
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T01-a", story_id="EPIC-x-S01-y", label="A", stage="pending"
        )
        tree = build_backlog_tree(tmp_path)
        assert tree["epics"][0]["stories"][0]["status"] == "pending"

    def test_zero_task_story_renders_numeric_zero_meta_not_blank(self, tmp_path: Path) -> None:
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-empty", epic_id="EPIC-x", seq=1, label="Empty")
        tree = build_backlog_tree(tmp_path)
        story = tree["epics"][0]["stories"][0]
        assert story["meta"] == "0 tasks"
        assert story["pct"] == "0%"

    def test_zero_story_epic_renders_numeric_zero_meta_not_blank(self, tmp_path: Path) -> None:
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        tree = build_backlog_tree(tmp_path)
        epic = tree["epics"][0]
        assert epic["meta"] == "0 stories"
        assert epic["pct"] == "0%"

    def test_current_task_id_picks_first_non_done_task_in_story_task_order(
        self, tmp_path: Path
    ) -> None:
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-y", epic_id="EPIC-x", seq=1, label="Y")
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T01-a", story_id="EPIC-x-S01-y", label="A", stage="done"
        )
        _write_task(
            tmp_path,
            id_="EPIC-x-S01-y-T02-b",
            story_id="EPIC-x-S01-y",
            label="B",
            stage="pending",
        )
        tree = build_backlog_tree(tmp_path)
        assert tree["currentTaskId"] == "EPIC-x-S01-y-T02-b"

    def test_current_task_id_empty_when_all_tasks_done(self, tmp_path: Path) -> None:
        _write_epic(tmp_path, id_="EPIC-x", label="X")
        _write_story(tmp_path, id_="EPIC-x-S01-y", epic_id="EPIC-x", seq=1, label="Y")
        _write_task(
            tmp_path, id_="EPIC-x-S01-y-T01-a", story_id="EPIC-x-S01-y", label="A", stage="done"
        )
        tree = build_backlog_tree(tmp_path)
        assert tree["currentTaskId"] == ""

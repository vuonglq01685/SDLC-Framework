"""Unit tests for engine/stop_pr_ready.py (Story 4.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.engine.stop_pr_ready import PrReadyStoryTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_TASKS_ROOT = "03-Implementation/tasks"
_STORY_A = "EPIC-a-S01-story-a"
_STORY_B = "EPIC-b-S01-story-b"
_TASK_A = f"{_STORY_A}-T01-first"
_TASK_B = f"{_STORY_B}-T01-first"


def _write_task(
    repo_root: Path,
    *,
    story_id: str,
    task_id: str,
    stage: str,
    filename: str = "T01-first-task.json",
) -> None:
    tasks = repo_root / _TASKS_ROOT / story_id
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / filename).write_text(
        json.dumps(
            {
                "id": task_id,
                "story_id": story_id,
                "label": "t",
                "stage": stage,
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )


def test_pr_ready_trigger_satisfies_protocol() -> None:
    assert isinstance(PrReadyStoryTrigger(), StopTrigger)


def test_check_fires_when_all_tasks_done(tmp_path: Path) -> None:
    _write_task(tmp_path, story_id=_STORY_A, task_id=_TASK_A, stage="done")
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(
        fired=True,
        trigger="pr_ready_story",
        target=_STORY_A,
        reason=f"/sdlc-publish-pr {_STORY_A}",
    )


def test_check_not_fired_when_any_task_not_done(tmp_path: Path) -> None:
    _write_task(tmp_path, story_id=_STORY_A, task_id=_TASK_A, stage="review")
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_tasks_directory_missing(tmp_path: Path) -> None:
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_story_has_zero_tasks(tmp_path: Path) -> None:
    empty_story = tmp_path / _TASKS_ROOT / _STORY_A
    empty_story.mkdir(parents=True)
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_multiple_stories_picks_lexically_first_pr_ready(tmp_path: Path) -> None:
    _write_task(tmp_path, story_id=_STORY_B, task_id=_TASK_B, stage="done")
    _write_task(tmp_path, story_id=_STORY_A, task_id=_TASK_A, stage="done")
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == _STORY_A


def test_check_ignores_stale_state_and_reads_disk(tmp_path: Path) -> None:
    _write_task(tmp_path, story_id=_STORY_A, task_id=_TASK_A, stage="done")
    stale = State(tasks={_TASK_A: {"id": _TASK_A, "stage": "pending"}})
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=stale)
    assert decision.fired is True
    assert decision.target == _STORY_A


def test_story_requires_all_tasks_done_not_just_one(tmp_path: Path) -> None:
    _write_task(
        tmp_path,
        story_id=_STORY_A,
        task_id=_TASK_A,
        stage="done",
        filename="T01-first-task.json",
    )
    _write_task(
        tmp_path,
        story_id=_STORY_A,
        task_id=f"{_STORY_A}-T02-second",
        stage="review",
        filename="T02-second-task.json",
    )
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_task_file_has_invalid_encoding(tmp_path: Path) -> None:
    # Review P1: a corrupt (non-UTF-8) task file must fail-safe (skip), not crash
    # the STOP check. UnicodeDecodeError is a ValueError subclass — it is NOT caught
    # by OSError/JSONDecodeError, so without the widened except it escapes check().
    tasks = tmp_path / _TASKS_ROOT / _STORY_A
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-corrupt.json").write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_non_task_json_in_story_dir_is_not_counted_as_a_task(tmp_path: Path) -> None:
    # Review P2: a stray non-task JSON (no canonical `T<nn>-<slug>` shape) must not be
    # globbed as a task. The tightened `T*-*.json` glob (parity with next_selector)
    # excludes `TODO.json`, so a story whose only file is `TODO.json` is NOT pr-ready.
    tasks = tmp_path / _TASKS_ROOT / _STORY_A
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "TODO.json").write_text(json.dumps({"stage": "done"}), encoding="utf-8")
    trigger = PrReadyStoryTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)

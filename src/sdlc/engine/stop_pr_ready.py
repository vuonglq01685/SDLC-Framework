"""STOP trigger 3 — pr-ready story detection (Story 4.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from sdlc.engine.stop_triggers import StopDecision
from sdlc.state.model import State

_TASKS_ROOT_REL: Final[str] = "03-Implementation/tasks"
_TASK_JSON_GLOB: Final[str] = "T*-*.json"


class PrReadyStoryTrigger:
    """Halt when a story is pr-ready (all tasks at stage ``done``)."""

    trigger_id = "pr_ready_story"

    def check(self, *, repo_root: Path, state: State) -> StopDecision:
        _ = state
        story_id = _first_pr_ready_story(repo_root)
        if story_id is None:
            return StopDecision(fired=False)
        return StopDecision(
            fired=True,
            trigger=self.trigger_id,
            target=story_id,
            reason=f"/sdlc-publish-pr {story_id}",
        )


def _first_pr_ready_story(repo_root: Path) -> str | None:
    tasks_root = repo_root / _TASKS_ROOT_REL
    if not tasks_root.is_dir():
        return None
    for story_dir in sorted(tasks_root.iterdir()):
        if not story_dir.is_dir():
            continue
        if _story_is_pr_ready(story_dir):
            return story_dir.name
    return None


def _story_is_pr_ready(story_dir: Path) -> bool:
    task_paths = list(story_dir.glob(_TASK_JSON_GLOB))
    if not task_paths:
        return False
    return all(_read_task_stage(task_path) == "done" for task_path in task_paths)


def _read_task_stage(task_path: Path) -> str | None:
    try:
        data = json.loads(task_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return None
        stage = data.get("stage")
        return stage if isinstance(stage, str) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

from __future__ import annotations

from typing import Final

from sdlc.errors import IdsError
from sdlc.ids.parsers import _SLUG_RE, EpicId, StoryId, TaskId

_MAX_ID_NUM: Final[int] = 99


def _check_int(value: object, component: str) -> None:
    # bool is a subclass of int but semantically wrong here — reject explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{component} must be int, got {type(value).__name__}")


def build_epic_id(epic_slug: str) -> EpicId:
    if not _SLUG_RE.match(epic_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "epic_slug", "value": epic_slug, "rule": "invalid_component"},
        )
    raw = f"EPIC-{epic_slug}"
    return EpicId(raw=raw, epic_slug=epic_slug)


def build_story_id(epic_slug: str, story_num: int, story_slug: str) -> StoryId:
    if not _SLUG_RE.match(epic_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "epic_slug", "value": epic_slug, "rule": "invalid_component"},
        )
    _check_int(story_num, "story_num")
    if not (0 <= story_num <= _MAX_ID_NUM):
        raise IdsError(
            f"story_num must be an integer in [0, {_MAX_ID_NUM}]",
            details={"component": "story_num", "value": story_num, "rule": "invalid_component"},
        )
    if not _SLUG_RE.match(story_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "story_slug", "value": story_slug, "rule": "invalid_component"},
        )
    raw = f"EPIC-{epic_slug}-S{story_num:02d}-{story_slug}"
    return StoryId(raw=raw, epic_slug=epic_slug, story_num=story_num, story_slug=story_slug)


def build_task_id(
    epic_slug: str,
    story_num: int,
    story_slug: str,
    task_num: int,
    task_slug: str,
) -> TaskId:
    if not _SLUG_RE.match(epic_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "epic_slug", "value": epic_slug, "rule": "invalid_component"},
        )
    _check_int(story_num, "story_num")
    if not (0 <= story_num <= _MAX_ID_NUM):
        raise IdsError(
            f"story_num must be an integer in [0, {_MAX_ID_NUM}]",
            details={"component": "story_num", "value": story_num, "rule": "invalid_component"},
        )
    if not _SLUG_RE.match(story_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "story_slug", "value": story_slug, "rule": "invalid_component"},
        )
    _check_int(task_num, "task_num")
    if not (0 <= task_num <= _MAX_ID_NUM):
        raise IdsError(
            f"task_num must be an integer in [0, {_MAX_ID_NUM}]",
            details={"component": "task_num", "value": task_num, "rule": "invalid_component"},
        )
    if not _SLUG_RE.match(task_slug):
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"component": "task_slug", "value": task_slug, "rule": "invalid_component"},
        )
    raw = f"EPIC-{epic_slug}-S{story_num:02d}-{story_slug}-T{task_num:02d}-{task_slug}"
    return TaskId(
        raw=raw,
        epic_slug=epic_slug,
        story_num=story_num,
        story_slug=story_slug,
        task_num=task_num,
        task_slug=task_slug,
    )

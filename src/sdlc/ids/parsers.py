from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from sdlc.errors import IdsError

_EPIC_ID_PATTERN: Final[str] = r"^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
# Public string patterns (Story 1.6 / 2A.11) — identical to the compiled regex sources.
EPIC_ID_PATTERN: Final[str] = _EPIC_ID_PATTERN
EPIC_ID_REGEX: Final[re.Pattern[str]] = re.compile(_EPIC_ID_PATTERN)

_STORY_ID_PATTERN: Final[str] = (
    r"^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
STORY_ID_PATTERN: Final[str] = _STORY_ID_PATTERN
STORY_ID_REGEX: Final[re.Pattern[str]] = re.compile(_STORY_ID_PATTERN)

_TASK_ID_PATTERN: Final[str] = (
    r"^EPIC-(?P<epic_slug>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"-S(?P<story_num>\d{2})-(?P<story_slug>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"-T(?P<task_num>\d{2})-(?P<task_slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
TASK_ID_PATTERN: Final[str] = _TASK_ID_PATTERN
TASK_ID_REGEX: Final[re.Pattern[str]] = re.compile(_TASK_ID_PATTERN)

# Private slug validator — imported by builders.py (intra-module; allowed by boundary rules).
_SLUG_PATTERN: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SLUG_RE: Final[re.Pattern[str]] = re.compile(_SLUG_PATTERN)


@dataclass(frozen=True, slots=True)
class EpicId:
    raw: str
    epic_slug: str


@dataclass(frozen=True, slots=True)
class StoryId:
    raw: str
    epic_slug: str
    story_num: int
    story_slug: str


@dataclass(frozen=True, slots=True)
class TaskId:
    raw: str
    epic_slug: str
    story_num: int
    story_slug: str
    task_num: int
    task_slug: str


def parse_epic_id(raw: str) -> EpicId:
    if not raw:
        raise IdsError(
            "identifier must be a non-empty string",
            details={"input": raw, "rule": "empty_or_non_string"},
        )
    if not raw.startswith("EPIC-"):
        raise IdsError(
            "epic identifier must start with 'EPIC-'",
            details={"input": raw, "rule": "missing_epic_prefix"},
        )
    m = EPIC_ID_REGEX.match(raw)
    if m is None:
        if STORY_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as a story identifier, not an epic identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        if TASK_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as a task identifier, not an epic identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        raise IdsError(
            "slug must be lowercase kebab-case",
            details={"input": raw, "rule": "invalid_slug"},
        )
    return EpicId(raw=raw, epic_slug=m.group("epic_slug"))


def parse_story_id(raw: str) -> StoryId:
    if not raw:
        raise IdsError(
            "identifier must be a non-empty string",
            details={"input": raw, "rule": "empty_or_non_string"},
        )
    if not raw.startswith("EPIC-"):
        raise IdsError(
            "story identifier must start with 'EPIC-'",
            details={"input": raw, "rule": "missing_epic_prefix"},
        )
    m = STORY_ID_REGEX.match(raw)
    if m is None:
        if EPIC_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as an epic identifier, not a story identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        if TASK_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as a task identifier, not a story identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        raise IdsError(
            "story identifier must contain '-S<NN>-' with a 2-digit story number",
            details={"input": raw, "rule": "invalid_story_shape"},
        )
    return StoryId(
        raw=raw,
        epic_slug=m.group("epic_slug"),
        story_num=int(m.group("story_num")),
        story_slug=m.group("story_slug"),
    )


def parse_task_id(raw: str) -> TaskId:
    if not raw:
        raise IdsError(
            "identifier must be a non-empty string",
            details={"input": raw, "rule": "empty_or_non_string"},
        )
    if not raw.startswith("EPIC-"):
        raise IdsError(
            "task identifier must start with 'EPIC-'",
            details={"input": raw, "rule": "missing_epic_prefix"},
        )
    m = TASK_ID_REGEX.match(raw)
    if m is None:
        if EPIC_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as an epic identifier, not a task identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        if STORY_ID_REGEX.match(raw):
            raise IdsError(
                "input parses as a story identifier, not a task identifier",
                details={"input": raw, "rule": "wrong_id_shape"},
            )
        raise IdsError(
            "task identifier must contain '-T<NN>-' with a 2-digit task number",
            details={"input": raw, "rule": "invalid_task_shape"},
        )
    return TaskId(
        raw=raw,
        epic_slug=m.group("epic_slug"),
        story_num=int(m.group("story_num")),
        story_slug=m.group("story_slug"),
        task_num=int(m.group("task_num")),
        task_slug=m.group("task_slug"),
    )

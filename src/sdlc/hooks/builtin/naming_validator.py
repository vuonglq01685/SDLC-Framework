"""naming_validator builtin hook — artifact id naming enforcement (FR36, AC4, Story 2A.4).

Validates that file stems under id-bearing directories match the canonical id regexes
from sdlc.ids.parsers (single source of truth — do NOT re-implement regex matching).

Scoped directories (per AC4):
  01-Requirement/04-Epics/           → EPIC_ID_REGEX
  01-Requirement/05-Stories/<epic>/  → STORY_ID_REGEX (+ validates parent epic dir)
  01-Requirement/06-Tasks/<epic>/<story>/  → TASK_ID_REGEX (+ validates both ancestors)

All other paths → allow (naming validation is scoped to id-bearing artifacts only).

This hook is NON-BYPASSABLE (AC6). Bypassing naming would corrupt the artifact-id
audit trail that sdlc trace and sdlc rebuild-state rely on.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

from sdlc.contracts.hook_payload import HookPayload
from sdlc.errors import IdsError
from sdlc.hooks.runner import HookDecision
from sdlc.ids.parsers import (
    _EPIC_ID_PATTERN,
    _STORY_ID_PATTERN,
    _TASK_ID_PATTERN,
    parse_epic_id,
    parse_story_id,
    parse_task_id,
)

_HOOK_NAME: Final[str] = "naming_validator"

_EPICS_DIR: Final[str] = "04-Epics"
_STORIES_DIR: Final[str] = "05-Stories"
_TASKS_DIR: Final[str] = "06-Tasks"
_REQ_DIR: Final[str] = "01-Requirement"

# Minimum parts counts for each id-bearing directory depth
_MIN_PARTS_REQ: Final[int] = 3  # [01-Requirement, <dir>, <file>]
_MIN_PARTS_STORY: Final[int] = 4  # [01-Requirement, 05-Stories, <epic>, <file>]
_MIN_PARTS_TASK: Final[int] = 5  # [01-Requirement, 06-Tasks, <epic>, <story>, <file>]


def _deny(reason: str) -> HookDecision:
    return HookDecision.deny(
        hook_name=_HOOK_NAME,
        reason=reason,
        error_code="naming_violation",
    )


def _validate_epic(stem: str) -> HookDecision:
    try:
        parse_epic_id(stem)
        return HookDecision.allow()
    except IdsError:
        return _deny(
            f"naming violation: {stem!r} does not match epic id regex /{_EPIC_ID_PATTERN}/"
        )


def _validate_story(stem: str, parent_epic_name: str) -> HookDecision:
    # Validate parent epic directory first (defense-in-depth)
    try:
        parse_epic_id(parent_epic_name)
    except IdsError:
        return _deny(f"parent directory {parent_epic_name!r} does not parse as an epic id")
    try:
        parse_story_id(stem)
        return HookDecision.allow()
    except IdsError:
        return _deny(
            f"naming violation: {stem!r} does not match story id regex /{_STORY_ID_PATTERN}/"
        )


def _validate_task(stem: str, parent_epic_name: str, parent_story_name: str) -> HookDecision:
    # Validate grandparent epic directory
    try:
        parse_epic_id(parent_epic_name)
    except IdsError:
        return _deny(f"parent directory {parent_epic_name!r} does not parse as an epic id")
    # Validate parent story directory
    try:
        parse_story_id(parent_story_name)
    except IdsError:
        return _deny(f"parent directory {parent_story_name!r} does not parse as a story id")
    try:
        parse_task_id(stem)
        return HookDecision.allow()
    except IdsError:
        return _deny(
            f"naming violation: {stem!r} does not match task id regex /{_TASK_ID_PATTERN}/"
        )


def naming_validator(payload: HookPayload) -> HookDecision:
    """Validate artifact id naming; non-id-bearing paths are allowed immediately."""
    path = PurePosixPath(payload.target_path)
    # PurePosixPath normalises "./" prefixes, so parts never start with ".".
    parts = path.parts

    # Must be under 01-Requirement/ and deep enough to have a directory entry
    if len(parts) < _MIN_PARTS_REQ or parts[0] != _REQ_DIR:
        return HookDecision.allow()

    dir_kind = parts[1]
    stem = PurePosixPath(parts[-1]).stem

    if dir_kind == _EPICS_DIR:
        return _validate_epic(stem)

    if dir_kind == _STORIES_DIR and len(parts) >= _MIN_PARTS_STORY:
        return _validate_story(stem, parent_epic_name=parts[2])

    if dir_kind == _TASKS_DIR and len(parts) >= _MIN_PARTS_TASK:
        return _validate_task(stem, parent_epic_name=parts[2], parent_story_name=parts[3])

    return HookDecision.allow()

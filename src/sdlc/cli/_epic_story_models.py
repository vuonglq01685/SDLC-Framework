"""Private CLI models for epic + story + task JSON artifacts (Story 2A.11, AC2/D2; Story 2A.16).

``_EpicEntry`` / ``_StoryEntry`` / ``_TaskEntry`` are underscore-prefixed StrictModel instances —
NOT promoted to ADR-024 wire-format snapshots (AC2/D2). Canonical on-disk JSON
uses :func:`serialize_entry` / :func:`serialize_task_entry` (human-readable indent=2).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.ids.parsers import (
    EPIC_ID_PATTERN,
    STORY_ID_PATTERN,
    STORY_ID_REGEX,
    TASK_ID_REGEX,
)

_RFC3339_Z: str = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"


class _EpicEntry(StrictModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, StringConstraints(pattern=EPIC_ID_PATTERN)]
    label: Annotated[str, StringConstraints(max_length=200)]
    priority: Literal["P0", "P1", "P2", "P3"]
    dependencies: tuple[Annotated[str, StringConstraints(pattern=EPIC_ID_PATTERN)], ...] = ()
    ordering: Annotated[int, Field(ge=0)]
    acceptance_criteria: tuple[Annotated[str, StringConstraints(max_length=1000)], ...] = Field(
        min_length=1,
    )
    drafted_at: Annotated[str, StringConstraints(pattern=_RFC3339_Z)]
    drafted_by_specialist: str


class _StoryEntry(StrictModel):
    schema_version: Literal[1] = 1
    id: Annotated[str, StringConstraints(pattern=STORY_ID_PATTERN)]
    epic_id: Annotated[str, StringConstraints(pattern=EPIC_ID_PATTERN)]
    seq: Annotated[int, Field(ge=1)]
    label: Annotated[str, StringConstraints(max_length=200)]
    as_a: Annotated[str, StringConstraints(max_length=200)]
    i_want: Annotated[str, StringConstraints(max_length=500)]
    so_that: Annotated[str, StringConstraints(max_length=500)]
    given_when_then: tuple[Annotated[str, StringConstraints(max_length=8000)], ...] = Field(
        min_length=1,
    )
    dependencies: tuple[Annotated[str, StringConstraints(pattern=STORY_ID_PATTERN)], ...] = ()
    drafted_at: Annotated[str, StringConstraints(pattern=_RFC3339_Z)]
    drafted_by_specialist: str
    # AC2/D1 (Story 2A.16): optional status field; private model, NOT snapshotted.
    # exclude=True keeps serialize_entry output byte-stable (no "status" key written).
    # Stories lacking this field default to "pending" (not active for /sdlc-break).
    # Story 2A.18 (/sdlc-next) will be the canonical writer; until then, manual edit.
    status: Literal["pending", "in-progress", "done"] = Field("pending", exclude=True)

    def model_post_init(self, __context: object) -> None:
        prefix = f"{self.epic_id}-S"
        if not self.id.startswith(prefix):
            raise ValueError(f"story id {self.id!r} must start with {prefix!r}")
        m = re.match(rf"^{re.escape(self.epic_id)}-S(\d{{2}})-", self.id)
        if m is None:
            raise ValueError(
                f"story id {self.id!r} missing S<NN> segment for epic {self.epic_id!r}",
            )
        if int(m.group(1)) != self.seq:
            raise ValueError(
                f"story id seq {m.group(1)!r} does not match field seq={self.seq}",
            )


class _TaskEntry(StrictModel):
    """Private model for /sdlc-break output, extended by /sdlc-task (Story 2A.17 AC8).

    NOT a wire-format contract (ADR-024 snapshot count unchanged).
    stage widened to 5-state machine; review_verdict/review_notes added for AC5 review capture.
    """

    id: str
    story_id: str
    label: Annotated[str, StringConstraints(min_length=1)]
    stage: Literal["pending", "write-tests", "write-code", "review", "done"] = "pending"
    dependencies: list[str] = Field(default_factory=list)
    review_verdict: Literal["approved", "rejected"] | None = Field(default=None)
    review_notes: str | None = Field(default=None)

    @field_validator("id")
    @classmethod
    def _id_regex(cls, v: str) -> str:
        if TASK_ID_REGEX.match(v) is None:
            raise ValueError(f"task id {v!r} does not match TASK_ID_REGEX")
        return v

    @field_validator("story_id")
    @classmethod
    def _story_id_regex(cls, v: str) -> str:
        if STORY_ID_REGEX.match(v) is None:
            raise ValueError(f"story_id {v!r} does not match STORY_ID_REGEX")
        return v

    @field_validator("dependencies")
    @classmethod
    def _deps_regex(cls, v: list[str]) -> list[str]:
        for dep in v:
            if TASK_ID_REGEX.match(dep) is None:
                raise ValueError(f"dependency {dep!r} does not match TASK_ID_REGEX")
        return v


def serialize_entry(entry: _EpicEntry | _StoryEntry) -> str:
    """Canonical JSON bytes for one epic or story file (AC2)."""
    return (
        json.dumps(
            entry.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ": "),
            indent=2,
        )
        + "\n"
    )


def serialize_task_entry(entry: _TaskEntry) -> str:
    """Canonical JSON bytes for one task file (Story 2A.16, AC5)."""
    return (
        json.dumps(
            entry.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ": "),
            indent=2,
        )
        + "\n"
    )


__all__ = ("_EpicEntry", "_StoryEntry", "_TaskEntry", "serialize_entry", "serialize_task_entry")

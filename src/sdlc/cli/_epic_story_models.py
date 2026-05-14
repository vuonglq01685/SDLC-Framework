"""Private CLI models for epic + story JSON artifacts (Story 2A.11, AC2/D2).

``_EpicEntry`` / ``_StoryEntry`` are underscore-prefixed StrictModel instances —
NOT promoted to ADR-024 wire-format snapshots (AC2/D2). Canonical on-disk JSON
uses :func:`serialize_entry` (human-readable indent=2; diverges from compact
``state.json`` per story AC2).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from sdlc.contracts._strict_model import StrictModel
from sdlc.ids.parsers import EPIC_ID_PATTERN, STORY_ID_PATTERN

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


__all__ = ("_EpicEntry", "_StoryEntry", "serialize_entry")

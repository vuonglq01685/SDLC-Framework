"""Minimal State model v1 — full schema in Stories 1.11-1.12 (Decision B5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class State(BaseModel):
    """`State` v1 projection (Architecture §520, §841).

    Skeleton schema for substrate stories 1.10-1.20. Additive shape changes
    within `schema_version=1` require both model and serialized-blob update;
    cross-version compat is owned by Story 1.19 migration framework.
    `extra="forbid"` rejects unknown fields so typos surface immediately at
    validation time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)

    schema_version: int = 1
    # Architecture §520: counter lives at state.json["next_monotonic_seq"]
    next_monotonic_seq: int = 0
    # SDLC phase 1=Requirement/2=Architecture/3=Implementation; default 1 for fresh projects.
    # Phase advancement (signoff-based) is Story 2A.12; v1 scanner returns 1 unconditionally.
    phase: int = 1
    epics: dict[str, Any] = Field(default_factory=dict)
    # Story records keyed by canonical story id (e.g. "EPIC-foo-S01-bar")
    stories: dict[str, Any] = Field(default_factory=dict)
    # Task records keyed by canonical task id (e.g. "EPIC-foo-S01-bar-T01-baz")
    tasks: dict[str, Any] = Field(default_factory=dict)
    # Story 4.1: auto-loop internal state (journal-replay derived, not wire-format)
    auto_loop_status: str = "idle"
    stop_reason: str | None = None

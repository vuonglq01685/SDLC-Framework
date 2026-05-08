"""Minimal State model v1 — full schema in Stories 1.11-1.12 (Decision B5)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class State(BaseModel):
    """Minimal v1 state projection (Architecture §520, §841).

    Full schema with journal-coupled hash fields is deferred to Stories 1.11-1.12.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)

    schema_version: int = 1
    # Architecture §520: counter lives at state.json["next_monotonic_seq"]
    next_monotonic_seq: int = 0
    # placeholder; full schema deferred to Story 1.11/1.12
    epics: dict[str, Any] = Field(default_factory=dict)

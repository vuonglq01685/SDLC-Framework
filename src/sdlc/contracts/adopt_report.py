"""Wire-format contract: `adopt-report.json` (Story 3.1, FR2, ADR-024 6th locked contract).

`sdlc init --adopt` writes `.claude/state/adopt-report.json` summarizing the brownfield
detection + adoption run. The file is read back on resume (Story 3.1 + 3.6), so it is a
cross-invocation compatibility surface — frozen at `schema_version=1` per epic-3-dag.md
Decision D1 (RATIFIED = wire-format) and registered in `_WIRE_FORMAT_REGISTRY`.

Encoding decisions (Story 3.1):
  * D2(a) — `confidence` is a strict `int` percent `[0,100]`. Architecture.md:494,515 forbids
    Python floats in `.claude/state/*` JSON; `strict=True` (StrictModel) rejects a `0.92`
    float at validation, forcing the integer-percent encoding.
  * D3(a) — `passes_completed` is the pass-level resume cursor a re-run reads to skip
    already-completed passes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel

# Mirrors contracts/journal_entry.py:11 — ISO-8601 UTC with optional sub-second + `Z`.
_RFC3339_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"

# epics.md:1803 — the canonical detected-artifact taxonomy.
ArtifactKind = Literal[
    "prd",
    "architecture",
    "research",
    "runbook",
    "ci-workflow",
    "build-file",
    "dockerfile",
    "readme",
    "unknown",
]


class DetectedArtifact(StrictModel):
    """A single pre-existing artifact discovered by Pass 1 detection (Story 3.2 populates)."""

    path: str
    kind: ArtifactKind
    confidence: int = Field(ge=0, le=100)
    suggested_target: str


class AdoptReport(StrictModel):
    """Summary of an `sdlc init --adopt` run (FR2, ADR-024 6th locked wire-format contract)."""

    schema_version: Literal[1] = 1
    repo_root: str
    scanned_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]
    detected: tuple[DetectedArtifact, ...] = Field(default_factory=tuple, strict=False)
    passes_completed: tuple[int, ...] = Field(default_factory=tuple, strict=False)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        # Mirrors journal_entry.py:28-33 — reject bool/str/float coercion into the version.
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

"""Wire-format contract: `adopted-symlinks.json` (Story 3.3, FR2, ADR-024 7th locked contract).

Pass 2 of `sdlc init --adopt` (`adopt/passes/symlink_offer.py`) records every accepted
symlink mapping into `.claude/state/adopted-symlinks.json`. The file is read back by Story 3.4
(stamp `imported_from_existing`), Story 3.5 (`sdlc adopt rollback`), and Story 3.6 (idempotency
recognition), so it is a cross-invocation compatibility surface — frozen at `schema_version=1`
and registered as the 7th entry in `_WIRE_FORMAT_REGISTRY` per ADR-024 (epic-3-dag.md D1).

Encoding decisions (mirrors `adopt_report.py`, Story 3.1):
  * `StrictModel` (`strict=True, extra="forbid", frozen=True`, ADR-025) — rejects lax coercion.
  * `schema_version: Literal[1]` with the `_strict_schema_version` before-validator (rejects
    bool/str/float coercion into the version, matching `journal_entry.py` / `adopt_report.py`).
  * `kind` reuses the frozen `ArtifactKind` taxonomy; `accepted_at` reuses the `_RFC3339_UTC`
    pattern — both imported from `adopt_report.py` so the two adopt contracts cannot drift.
  * `mappings` is a `tuple[..., ...] = Field(default_factory=tuple, strict=False)` — the
    StrictModel container opt-out convention (accepts list inputs from JSON parsers).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.contracts.adopt_report import _RFC3339_UTC, ArtifactKind


class SymlinkMapping(StrictModel):
    """One accepted adopt symlink: a canonical SDLC slot (``target``) → pre-existing ``source``."""

    source: str
    target: str
    accepted_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]
    kind: ArtifactKind


class AdoptedSymlinks(StrictModel):
    """Accepted symlink manifest for an `sdlc init --adopt` run (ADR-024 7th locked contract)."""

    schema_version: Literal[1] = 1
    mappings: tuple[SymlinkMapping, ...] = Field(default_factory=tuple, strict=False)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        # Mirrors adopt_report.py:59-65 — reject bool/str/float coercion into the version.
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

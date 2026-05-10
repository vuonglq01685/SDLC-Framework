"""StrictModel — pydantic v2 strict-mode base for all wire-format contracts (ADR-025)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(
    BaseModel
):  # strict-opt-out: this IS the strict-mode base — BaseModel is intentional
    """Strict-mode base for all contracts in src/sdlc/contracts/.

    Provides:
      strict=True    — rejects lax scalar coercion (bool-as-int, float-as-int, etc.)
      extra="forbid" — unknown fields raise ValidationError
      frozen=True    — instances are immutable after construction

    Container fields (tuple, Mapping) that accept list inputs from YAML parsers
    must explicitly opt out with Field(..., strict=False).
    """

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
    )

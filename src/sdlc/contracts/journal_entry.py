from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_serializer, field_validator

from sdlc.contracts._strict_model import StrictModel

_RFC3339_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
_SHA256 = r"^sha256:[0-9a-f]{64}$"


class JournalEntry(StrictModel):
    """Wire-format contract: append-only journal record (Architecture §595-§606, Decision B3)."""

    schema_version: Literal[1] = 1
    monotonic_seq: int = Field(ge=0)
    ts: Annotated[str, StringConstraints(pattern=_RFC3339_UTC)]
    actor: str
    kind: str
    target_id: str
    before_hash: Annotated[str, StringConstraints(pattern=_SHA256)] | None
    after_hash: Annotated[str, StringConstraints(pattern=_SHA256)]
    payload: Mapping[str, object] = Field(default_factory=dict, strict=False)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("payload", mode="after")
    @classmethod
    def _freeze_payload(cls, v: Mapping[str, object]) -> Mapping[str, object]:
        return MappingProxyType(dict(v))

    @field_serializer("payload")
    def _serialize_payload(self, v: Mapping[str, object]) -> dict[str, object]:
        return dict(v)

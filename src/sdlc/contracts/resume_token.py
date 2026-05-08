from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

_SHA256 = r"^sha256:[0-9a-f]{64}$"


class ResumeToken(BaseModel):
    """Wire-format contract: resume-from-checkpoint token (Architecture §608-§613)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    schema_version: Literal[1] = 1
    phase: int = Field(ge=0)
    cursor: Mapping[str, object] = Field(default_factory=dict)
    suggested_next_command: str
    state_hash: Annotated[str, StringConstraints(pattern=_SHA256)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("cursor", mode="after")
    @classmethod
    def _freeze_cursor(cls, v: Mapping[str, object]) -> Mapping[str, object]:
        return MappingProxyType(dict(v))

    @field_serializer("cursor")
    def _serialize_cursor(self, v: Mapping[str, object]) -> dict[str, object]:
        return dict(v)

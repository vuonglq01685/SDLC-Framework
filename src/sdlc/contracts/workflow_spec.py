from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class WorkflowSpec(BaseModel):
    """Wire-format contract: workflow YAML specification (Architecture §634-§643)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    schema_version: Literal[1] = 1
    name: str
    slash_command: str
    primary_agent: str
    parallel_agents: tuple[str, ...] = Field(default_factory=tuple)
    synthesizer_agent: str | None = None
    postconditions: tuple[str, ...] = Field(default_factory=tuple)
    write_globs: Mapping[str, tuple[str, ...]]
    stop_on_postcondition_failure: bool = Field(default=True, strict=True)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("write_globs", mode="after")
    @classmethod
    def _freeze_write_globs(cls, v: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(v))

    @field_serializer("write_globs")
    def _serialize_write_globs(self, v: Mapping[str, tuple[str, ...]]) -> dict[str, list[str]]:
        return {k: list(val) for k, val in v.items()}

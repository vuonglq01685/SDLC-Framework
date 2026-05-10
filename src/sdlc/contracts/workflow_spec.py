from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import Field, field_serializer, field_validator

from sdlc.contracts._strict_model import StrictModel


class WorkflowSpec(StrictModel):
    """Wire-format contract: workflow YAML specification (Architecture §634-§643)."""

    schema_version: Literal[1] = 1
    name: str
    slash_command: str
    primary_agent: str
    # strict=False: YAML parsers return lists; coercion to tuple is expected.
    parallel_agents: tuple[str, ...] = Field(default_factory=tuple, strict=False)
    synthesizer_agent: str | None = None
    postconditions: tuple[str, ...] = Field(default_factory=tuple, strict=False)
    # strict=False: YAML dict values are lists; inner list→tuple coercion is expected.
    write_globs: Mapping[str, tuple[str, ...]] = Field(strict=False)
    stop_on_postcondition_failure: bool = Field(default=True)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("write_globs", mode="before")
    @classmethod
    def _coerce_write_globs_inner_lists(cls, v: object) -> object:
        """Coerce list values to tuples before strict validation.

        YAML parsers return lists for sequences; write_globs values must be
        tuple[str, ...] in the validated model, so we pre-coerce here.
        """
        if isinstance(v, Mapping):
            return {k: tuple(val) if isinstance(val, list) else val for k, val in v.items()}
        return v

    @field_validator("write_globs", mode="after")
    @classmethod
    def _freeze_write_globs(cls, v: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(v))

    @field_serializer("write_globs")
    def _serialize_write_globs(self, v: Mapping[str, tuple[str, ...]]) -> dict[str, list[str]]:
        return {k: list(val) for k, val in v.items()}

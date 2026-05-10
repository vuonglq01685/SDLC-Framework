from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from sdlc.contracts._strict_model import StrictModel


class SpecialistFrontmatter(StrictModel):
    """Wire-format contract: specialist YAML frontmatter (Architecture §623-§632)."""

    schema_version: Literal[1] = 1
    name: str
    title: str
    icon: str = Field(min_length=1, max_length=4)
    model: str
    # strict=False: YAML parsers return lists; coercion to tuple is expected.
    tools: tuple[str, ...] = Field(default_factory=tuple, strict=False)
    read_globs: tuple[str, ...] = Field(default_factory=tuple, strict=False)
    write_globs: tuple[str, ...] = Field(default_factory=tuple, strict=False)
    description: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

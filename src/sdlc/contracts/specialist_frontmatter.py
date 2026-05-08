from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpecialistFrontmatter(BaseModel):
    """Wire-format contract: specialist YAML frontmatter (Architecture §623-§632)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    schema_version: Literal[1] = 1
    name: str
    title: str
    icon: str = Field(min_length=1, max_length=4)
    model: str
    tools: tuple[str, ...] = Field(default_factory=tuple)
    read_globs: tuple[str, ...] = Field(default_factory=tuple)
    write_globs: tuple[str, ...] = Field(default_factory=tuple)
    description: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

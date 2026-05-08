from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

_SHA256 = r"^sha256:[0-9a-f]{64}$"


class HookPayload(BaseModel):
    """Wire-format contract: pre-write hook payload (Architecture §615-§621, Decision D2)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    schema_version: Literal[1] = 1
    hook_name: str
    target_path: str
    target_kind: str
    content_hash_before: Annotated[str, StringConstraints(pattern=_SHA256)] | None
    write_intent: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

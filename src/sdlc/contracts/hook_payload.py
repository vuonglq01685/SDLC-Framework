from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel

_SHA256 = r"^sha256:[0-9a-f]{64}$"


class HookPayload(StrictModel):
    """Wire-format contract: pre-write hook payload (Architecture §615-§621, Decision D2)."""

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

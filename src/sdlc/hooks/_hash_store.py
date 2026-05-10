"""Private pydantic model for the hook-hashes.json policy file.

This is internal policy state, NOT a wire-format contract — see Story 2A.5
AC8. Format may evolve in v1.x without ADR-024 ceremony.

Split out of ``tampering.py`` (DR1 + P8 LOC cap) so that the public detection
surface stays under the 250 LOC budget.
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

from pydantic import StringConstraints, field_validator

from sdlc.contracts._strict_model import StrictModel

# Strict ms-precision RFC 3339 UTC (P15 — was `(\.\d+)?Z$`, accepted microseconds).
_RFC3339_UTC_MS: Final[str] = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
_SHA256_PAT: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
# P16: forbid NUL bytes, leading `/`, and parent-traversal `..` segments in keys.
_RELPATH_FORBID: Final[re.Pattern[str]] = re.compile(r"\x00|^/|(?:^|/)\.\.(?:$|/)")

SCHEMA_VERSION: Final[int] = 1
HOOKS_ROOT_LABEL: Final[str] = ".claude/hooks"


class _HookHashStore(StrictModel):
    schema_version: Literal[1] = 1
    trusted_at: Annotated[str, StringConstraints(pattern=_RFC3339_UTC_MS)]
    hooks_root: str
    hashes: dict[str, str]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        # `bool` is a subclass of `int`, but `type(True) is int` returns False.
        # Keep an explicit bool check anyway for readability.
        if isinstance(v, bool) or type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v

    @field_validator("hooks_root", mode="after")
    @classmethod
    def _validate_hooks_root(cls, v: str) -> str:
        # P14: pin the label so a hand-edited or attacker-staged store cannot
        # silently rebind hooks_root to ../../etc.
        if v != HOOKS_ROOT_LABEL:
            raise ValueError(f"hooks_root must be {HOOKS_ROOT_LABEL!r}, got {v!r}")
        return v

    @field_validator("hashes", mode="after")
    @classmethod
    def _validate_and_sort_hashes(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if _RELPATH_FORBID.search(key):  # P16
                raise ValueError(f"hash key {key!r} contains forbidden chars (NUL, leading /, ..)")
            if not _SHA256_PAT.match(val):
                raise ValueError(f"hash value for {key!r} must match sha256:<64hex>, got {val!r}")
        return dict(sorted(v.items()))


__all__ = ["HOOKS_ROOT_LABEL", "SCHEMA_VERSION", "_HookHashStore"]

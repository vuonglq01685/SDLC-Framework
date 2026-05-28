from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from sdlc.errors.base import (
    AdoptError,
    CompatibilityError,
    ConfigError,
    DispatchError,
    HookError,
    IdsError,
    JournalError,
    MockMissError,
    SchemaError,
    SdlcError,
    SecurityError,
    SignoffError,
    SpecialistError,
    StateError,
    WorkflowError,
)

EXIT_CODE_MAP: Final[Mapping[str, int]] = MappingProxyType(SdlcError.EXIT_CODE_MAP)

# Explicit semantic order per Story 1.6 AC6 (root → architecture-canonical 8 →
# story-1.6 IdsError addition → MockMissError → EXIT_CODE_MAP); do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "SdlcError",
    "StateError",
    "JournalError",
    "DispatchError",
    "HookError",
    "SchemaError",
    "SignoffError",
    "AdoptError",
    "CompatibilityError",
    "ConfigError",
    "IdsError",
    "MockMissError",
    "WorkflowError",
    "SecurityError",
    "SpecialistError",
    "EXIT_CODE_MAP",
)

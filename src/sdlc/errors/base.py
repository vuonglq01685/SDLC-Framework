from __future__ import annotations

from typing import ClassVar


class SdlcError(Exception):
    """Root exception for the SDLC framework (Architecture §529)."""

    code: ClassVar[str] = "ERR_SDLC"
    EXIT_CODE_MAP: ClassVar[dict[str, int]] = {
        "ERR_CONFIG": 1,
        "ERR_IDS": 1,
        "ERR_STATE": 2,
        "ERR_JOURNAL": 2,
        "ERR_DISPATCH": 2,
        "ERR_SCHEMA": 2,
        "ERR_SIGNOFF": 2,
        "ERR_HOOK": 2,
        "ERR_ADOPT": 2,
        "ERR_COMPATIBILITY": 3,
    }

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.details: dict[str, object] = dict(details) if details else {}

    @property
    def exit_code(self) -> int:
        return self.EXIT_CODE_MAP.get(self.code, 2)

    def to_envelope(self) -> dict[str, object]:
        inner: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "exit_code": self.exit_code,
        }
        return {"error": inner}


class StateError(SdlcError):
    code: ClassVar[str] = "ERR_STATE"


class JournalError(SdlcError):
    code: ClassVar[str] = "ERR_JOURNAL"


class DispatchError(SdlcError):
    code: ClassVar[str] = "ERR_DISPATCH"


class HookError(SdlcError):
    code: ClassVar[str] = "ERR_HOOK"


class SchemaError(SdlcError):
    code: ClassVar[str] = "ERR_SCHEMA"


class SignoffError(SdlcError):
    code: ClassVar[str] = "ERR_SIGNOFF"


class AdoptError(SdlcError):
    code: ClassVar[str] = "ERR_ADOPT"


class ConfigError(SdlcError):
    code: ClassVar[str] = "ERR_CONFIG"


class IdsError(SdlcError):
    code: ClassVar[str] = "ERR_IDS"


class WorkflowError(SdlcError):
    code: ClassVar[str] = "ERR_WORKFLOW"


class MockMissError(DispatchError):
    """MockAIRuntime missing-fixture or malformed-fixture error.

    Raised at construction time (fixtures_dir doesn't exist, malformed YAML)
    and at dispatch time (no fixture matches (workflow_step, prompt_hash)).
    Inherits ERR_DISPATCH code so abstraction-adequacy tests propagate it
    identically to a real Claude dispatch failure.
    """


class SpecialistError(SdlcError):
    """Specialist registry / manifest / frontmatter validation error (Story 2A.2)."""

    code: ClassVar[str] = "ERR_SPECIALIST"


class CompatibilityError(SdlcError):
    """External Claude Code binary missing or below the documented minimum (Story 2B.2)."""

    code: ClassVar[str] = "ERR_COMPATIBILITY"

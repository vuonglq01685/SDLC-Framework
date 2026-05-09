"""Schema-version gate for state.json (FR5, FR48, NFR-DR-2, Architecture §844, §1135).

The framework refuses to start if state.json's schema_version does not
match CURRENT_SCHEMA_VERSION. The error message names the exact
`sdlc migrate-vN` command. Bypass via read_state_raw is reserved for
migration scripts and rebuild-state recovery (Story 1.20).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from sdlc.errors import SchemaError, StateError
from sdlc.state.model import State

CURRENT_SCHEMA_VERSION: Final[int] = 1
_STATE_SCHEMA_VERSION_KEY: Final[str] = "schema_version"
_REFUSAL_MSG_FORMAT: Final[str] = (
    "schema_version mismatch: state is v{state}, framework expects v{framework};"
    " run `sdlc migrate-v{framework}`"
)

__all__ = (
    "CURRENT_SCHEMA_VERSION",
    "read_state_or_refuse",
    "read_state_raw",
)


def read_state_or_refuse(target: Path) -> State | None:
    """Read and parse state.json with the schema-version gate.

    Returns None if target does not exist.
    Raises SchemaError if schema_version mismatches CURRENT_SCHEMA_VERSION.
    Raises StateError on malformed JSON, OS errors, or missing schema_version.
    """
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StateError(
            f"state.json contains invalid JSON: {e}",
            details={"path": str(target), "reason": "json"},
        ) from e
    except OSError as e:
        raise StateError(
            f"state.json could not be read: {e}",
            details={"path": str(target), "errno": e.errno, "reason": "io"},
        ) from e

    if not isinstance(payload, dict):
        raise StateError(
            "state.json must be a JSON object",
            details={"path": str(target), "reason": "not_object"},
        )

    if _STATE_SCHEMA_VERSION_KEY not in payload:
        raise StateError(
            "state.json missing schema_version",
            details={"path": str(target), "reason": "missing_schema_version"},
        )

    file_version = payload[_STATE_SCHEMA_VERSION_KEY]
    if file_version != CURRENT_SCHEMA_VERSION:
        raise SchemaError(
            _REFUSAL_MSG_FORMAT.format(state=file_version, framework=CURRENT_SCHEMA_VERSION),
            details={
                "path": str(target),
                "state_schema_version": file_version,
                "framework_schema_version": CURRENT_SCHEMA_VERSION,
                "remediation": f"sdlc migrate-v{CURRENT_SCHEMA_VERSION}",
                "reason": "schema_version_mismatch",
            },
        )

    try:
        return State.model_validate(payload)
    except (ValueError, TypeError) as e:
        raise StateError(
            f"state.json failed schema validation: {e}",
            details={"path": str(target), "reason": "schema"},
        ) from e


def read_state_raw(target: Path) -> dict[str, Any] | None:
    """Read state.json bypassing the schema gate and pydantic validation.

    Returns None if target does not exist. Returns the raw dict.
    Raises StateError on JSON/OS errors or non-object root.

    Use only from `cli/migrate.py` and `state/rebuild.py` (Story 1.20).
    Production read paths MUST use `read_state_or_refuse` to enforce the schema gate.
    """
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StateError(
            f"state.json contains invalid JSON: {e}",
            details={"path": str(target), "reason": "json"},
        ) from e
    except OSError as e:
        raise StateError(
            f"state.json could not be read: {e}",
            details={"path": str(target), "errno": e.errno, "reason": "io"},
        ) from e

    if not isinstance(payload, dict):
        raise StateError(
            "state.json must be a JSON object",
            details={"path": str(target), "reason": "not_object"},
        )

    return payload

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
_RECOVERY_MSG_FORMAT: Final[str] = (
    "state.json is malformed at {state_path}. To recover: run"
    " `sdlc rebuild-state` (rebuilds from journal) or"
    " `sdlc migrate-vN` (if version mismatch)."
    " The journal at {journal_path} is untouched."
)

__all__ = (  # noqa: RUF022
    "CURRENT_SCHEMA_VERSION",
    "read_state_or_refuse",
    "read_state_or_recover",  # Story 1.20
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


def read_state_or_recover(state_path: Path, journal_path: Path) -> State | None:
    """Canonical CLI-side state reader — wraps read_state_or_refuse with a recovery prompt.

    Returns None if state_path does not exist (missing state is not a malformation).

    Re-raises ``read_state_or_refuse``'s ``SchemaError`` and ``StateError`` as a
    ``StateError`` whose message is the unified recovery prompt naming both
    ``state_path`` and ``journal_path``. ``read_state_or_refuse`` already wraps
    ``json.JSONDecodeError``, ``OSError``, missing-schema-version, non-object root,
    and pydantic ``ValidationError`` (via the broad ``ValueError, TypeError`` catch
    on ``State.model_validate``) into ``StateError`` — so this function transitively
    covers all malformation classes through the StateError branch.

    Use this function from any CLI subcommand that reads state.json. It composes
    Story 1.19's ``read_state_or_refuse`` schema gate with the Story 1.20
    recovery-prompt formatter.

    journal_path is purely for message formatting — this function does NOT read
    the journal. The "is untouched" wording reassures users that the journal (the
    source of truth per Decision B5) is safe and recovery is possible.

    ADR-023 mandates callers pass canonical resolved paths so the recovery prompt
    names a stable absolute path; ``cli/scan.py`` and ``cli/status.py`` ``.resolve()``
    both arguments before invocation.
    """
    if not state_path.exists():
        return None
    try:
        return read_state_or_refuse(state_path)
    except SchemaError as err:
        recovery_msg = _RECOVERY_MSG_FORMAT.format(state_path=state_path, journal_path=journal_path)
        merged_details: dict[str, object] = {
            **err.details,
            "state_path": str(state_path),
            "journal_path": str(journal_path),
            "reason": "schema_version_mismatch",
            "inner_message": err.message,
            "remediation_primary": "sdlc rebuild-state",
            "remediation_alternative": err.details.get("remediation"),
        }
        raise StateError(recovery_msg, details=merged_details) from err
    except StateError as err:
        recovery_msg = _RECOVERY_MSG_FORMAT.format(state_path=state_path, journal_path=journal_path)
        merged_details = {
            **err.details,
            "state_path": str(state_path),
            "journal_path": str(journal_path),
            "inner_message": err.message,
            "remediation_primary": "sdlc rebuild-state",
            "remediation_alternative": "sdlc migrate-vN",
        }
        raise StateError(recovery_msg, details=merged_details) from err


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

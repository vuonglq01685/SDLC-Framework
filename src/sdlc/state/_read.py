"""Cross-platform reader for state.json.

`atomic.py` is POSIX-only because the write protocol needs `fcntl` and parent-dir
fsync (Architecture §573). Reading does not — the atomic rename guarantees no torn
reads on POSIX, and Story 1.16's Windows fallback (`Path.write_bytes` for the
canonical bytes) is whole-file and equally torn-free. Hosting `read_state` here
lets `cli/scan.py` and `cli/status.py` use one cross-platform reader instead of
forking a `_read_state_portable` helper per command (see ADR-020 §Consequences).
"""

from __future__ import annotations

import json
from pathlib import Path

from sdlc.errors import StateError
from sdlc.state.model import State


def read_state(target: Path) -> State | None:
    """Read and parse state.json (no hash verification — deferred to Story 1.12).

    Returns None if target does not exist; raises StateError on JSON or schema errors.
    Cross-platform: pure stdlib, no `fcntl`. Story 1.10's atomic rename provides the
    no-torn-reads guarantee on POSIX; Story 1.16's `Path.write_bytes` fallback does
    the same on Windows.
    """
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8")
        payload = json.loads(text)
        return State.model_validate(payload)
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
    except (ValueError, TypeError) as e:
        # pydantic.ValidationError subclasses ValueError; ValueError/TypeError cover
        # schema violations without swallowing programmer errors like NameError or
        # AttributeError that would indicate a bug rather than data corruption.
        raise StateError(
            f"state.json failed schema validation: {e}",
            details={"path": str(target), "reason": "schema"},
        ) from e

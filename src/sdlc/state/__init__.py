from __future__ import annotations

import json as _json
import sys

from sdlc.state._read import read_state
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

# atomic.py is POSIX-only; only the WRITE protocol needs fcntl + parent-dir fsync
# (Architecture §573). read_state is cross-platform and lives in state/_read.py.
if sys.platform != "win32":
    from sdlc.state.atomic import write_state_atomic, write_state_atomic_sync
else:

    def write_state_atomic(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic is POSIX-only — see Architecture §573")

    def write_state_atomic_sync(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic_sync is POSIX-only — see Architecture §573")


def state_to_canonical_bytes(state: State) -> bytes:
    """Serialize a State to canonical bytes (sort_keys, no ascii escaping, compact, trailing \\n).

    One source of truth shared by cli/init.py (Story 1.16) and cli/scan.py (Story 1.17)
    so the canonical-bytes contract cannot drift between the two writers. Mirrors the
    contract used by state/atomic.py's write protocol.
    """
    payload = state.model_dump(mode="json")
    return (
        _json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


# Semantic order: model → write-async → write-sync → read → projection → bytes; do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "State",
    "write_state_atomic",
    "write_state_atomic_sync",
    "read_state",
    "project_from_journal",
    "state_to_canonical_bytes",
)

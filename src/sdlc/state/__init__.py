from __future__ import annotations

import json as _json
import sys

from sdlc.state._read import read_state
from sdlc.state.model import State
from sdlc.state.projection import project_from_journal
from sdlc.state.reader import CURRENT_SCHEMA_VERSION, read_state_or_refuse, read_state_raw

# atomic.py is POSIX-only; only the WRITE protocol needs fcntl + parent-dir fsync
# (Architecture §573). read_state is cross-platform and lives in state/_read.py.
if sys.platform != "win32":
    from sdlc.state.atomic import (
        write_state_atomic,
        write_state_atomic_sync,
        write_state_raw_atomic_sync,
    )
    from sdlc.state.reader import read_state_or_recover
    from sdlc.state.rebuild import rebuild_state_from_journal
else:

    def write_state_atomic(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic is POSIX-only — see Architecture §573")

    def write_state_atomic_sync(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic_sync is POSIX-only — see Architecture §573")

    def write_state_raw_atomic_sync(*_: object, **__: object) -> None:
        raise NotImplementedError(
            "write_state_raw_atomic_sync is POSIX-only — see Architecture §573"
        )

    def rebuild_state_from_journal(*_: object, **__: object) -> int:
        raise NotImplementedError(
            "rebuild_state_from_journal is POSIX-only — see Architecture §573"
        )

    def read_state_or_recover(*_: object, **__: object) -> None:
        raise NotImplementedError("read_state_or_recover is POSIX-only — see Architecture §573")


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


# Semantic order: model → write-async → write-sync → write-raw → read → read-or-refuse
# → read-or-recover → read-raw → projection → rebuild → bytes → schema-version; do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "State",
    "write_state_atomic",
    "write_state_atomic_sync",
    "write_state_raw_atomic_sync",
    "read_state",
    "read_state_or_refuse",
    "read_state_or_recover",
    "read_state_raw",
    "project_from_journal",
    "rebuild_state_from_journal",  # Story 1.20
    "state_to_canonical_bytes",
    "CURRENT_SCHEMA_VERSION",
)

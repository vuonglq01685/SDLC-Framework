from __future__ import annotations

import sys

from sdlc.state.model import State
from sdlc.state.projection import project_from_journal

# atomic.py is POSIX-only; import is conditional on platform
if sys.platform != "win32":
    from sdlc.state.atomic import read_state, write_state_atomic, write_state_atomic_sync
else:

    def write_state_atomic(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic is POSIX-only — see Architecture §573")

    def write_state_atomic_sync(*_: object, **__: object) -> None:
        raise NotImplementedError("write_state_atomic_sync is POSIX-only — see Architecture §573")

    def read_state(*_: object, **__: object) -> None:
        raise NotImplementedError("read_state is POSIX-only — see Architecture §573")


# Semantic order: model → write (async) → write (sync) → read → projection; do NOT alphabetize.
__all__ = (  # noqa: RUF022
    "State",
    "write_state_atomic",
    "write_state_atomic_sync",
    "read_state",
    "project_from_journal",
)

"""Cross-platform reader for state.json.

`atomic.py` is POSIX-only because the write protocol needs `fcntl` and parent-dir
fsync (Architecture §573). Reading does not — the atomic rename guarantees no torn
reads on POSIX, and Story 1.16's Windows fallback (`Path.write_bytes` for the
canonical bytes) is whole-file and equally torn-free. Hosting `read_state` here
lets `cli/scan.py` and `cli/status.py` use one cross-platform reader instead of
forking a `_read_state_portable` helper per command (see ADR-020 §Consequences).

Story 1.19: delegates to `read_state_or_refuse` so all callers transparently get
the schema-version gate without any import changes.
"""

from __future__ import annotations

from pathlib import Path

from sdlc.state.model import State
from sdlc.state.reader import read_state_or_refuse


def read_state(target: Path) -> State | None:
    """Read and parse state.json with the schema-version gate (Story 1.19).

    Delegates to sdlc.state.reader.read_state_or_refuse so existing callers
    from Stories 1.16-1.17 transparently get refusal behavior on schema mismatch.
    Returns None if target does not exist; raises StateError or SchemaError otherwise.
    """
    return read_state_or_refuse(target)

"""Genesis hash for journal chain entries with no prior state.

Used by all `JournalEntry` whose ``target_id`` has never been written before
(e.g. first ``hooks_trusted`` from ``sdlc init``, first ``signoff_recorded``
from a future story, etc.).

Defined as ``sha256(b"")`` — the canonical "no prior content existed" hash.

This constant exists so that ``before_hash`` is *always* a valid sha256-shape
string. The chain-of-hashes invariant (replay/audit) can then be validated
uniformly across all ``kind`` values without per-kind carve-outs.

See Story 2A.5 DR5 (code review 2026-05-10) for the design rationale —
the alternative was to allow ``before_hash=None`` for genesis entries,
which proliferated per-kind special cases in the chain validator.
"""

from __future__ import annotations

from typing import Final

# sha256 of empty bytes; verified via:
#   python3 -c "import hashlib; print(hashlib.sha256(b'').hexdigest())"
GENESIS_HASH: Final[str] = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


__all__ = ["GENESIS_HASH"]

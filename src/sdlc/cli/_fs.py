"""Filesystem helpers shared across CLI write sites (P13).

Single source of truth so journal-chain ``before_hash``/``after_hash`` shapes
are byte-identical across producers. Previously three near-duplicate
``_sha256_file_or_none`` / ``_sha256_file`` / ``_compute_sha256_of_file``
helpers existed across ``scan.py``, ``trust_hooks.py``, ``init.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file_or_none(path: Path) -> str | None:
    """Return ``sha256:<hex>`` for a file's content, or ``None`` if missing.

    Streams via ``hashlib.file_digest`` (Python 3.11+) so memory is bounded
    regardless of file size — relevant when the path points to a non-trivial
    state.json or hook-hashes.json under unusual conditions.
    """
    if not path.exists():
        return None
    with path.open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()  # type: ignore[attr-defined]  # 3.11+
    return f"sha256:{digest}"


__all__ = ["sha256_file_or_none"]

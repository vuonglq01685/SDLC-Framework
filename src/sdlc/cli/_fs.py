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
    regardless of file size. On Python 3.10 (requires-python floor) file_digest
    is absent, so a chunked fallback keeps memory bounded with identical output.
    """
    if not path.exists():
        return None
    with path.open("rb") as fh:
        if hasattr(hashlib, "file_digest"):
            digest = hashlib.file_digest(fh, "sha256").hexdigest()
        else:  # Python 3.10 — file_digest added in 3.11
            _h = hashlib.sha256()
            while _chunk := fh.read(1 << 16):
                _h.update(_chunk)
            digest = _h.hexdigest()
    return f"sha256:{digest}"


__all__ = ["sha256_file_or_none"]

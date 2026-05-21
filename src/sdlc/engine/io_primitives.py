"""Atomic raw-text write primitive (Epic 2A retro D1/C1, ADR-031).

Bridges the gap between ``state/atomic.py`` (state.json-specific, JSON-canonical) and the
17 ``Path.write_text()`` callsites scattered across ``cli/_*_pipeline.py`` plus
``dispatcher/_panel_helpers.py``. Same 7-step POSIX protocol as ``state/atomic.py``
PLUS explicit EINTR retry on ``os.write`` and ``os.replace``.

Closes ``EPIC-1-D3-EINTR-RETRY`` + ``EPIC-2A-D1-WRITE-PRIMITIVE``.

Skeleton only — implementation lands in C1 GREEN step.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":  # pragma: no cover - POSIX-only invariant per Architecture §573
    raise ImportError(
        "sdlc.engine.io_primitives is POSIX-only — fcntl + parent-dir fsync are required"
    )

import os
from pathlib import Path
from typing import Final

# Re-exported for tests; mocks patch ``io_primitives.os.write`` /
# ``io_primitives.os.replace`` / ``io_primitives.os.open``.
__all__ = ["atomic_write", "atomic_write_bytes", "os"]

_TMP_SUFFIX: Final[str] = ".tmp"
_LOCK_SUFFIX: Final[str] = ".lock"

# EINTR retry budget for os.write and os.replace. 16 retries of a microsecond-
# scale syscall is well under any meaningful operator-visible latency. Beyond
# 16 EINTRs in sequence indicates a pathological signal-storm, not a
# recoverable interrupt.
_MAX_EINTR_RETRIES: Final[int] = 16


def atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically via tmp + rename + fsync (EINTR-safe).

    Caller responsibilities:
      - ``path`` must be absolute. ValueError on relative.
      - Parent directory must already exist. NotADirectoryError otherwise.
      - No concurrent writer holding the ``.lock`` sentinel.
    """
    raise NotImplementedError("C1 GREEN")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Byte-oriented variant of :func:`atomic_write`."""
    raise NotImplementedError("C1 GREEN")

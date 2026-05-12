"""Crash-safe write primitive for `sdlc verify` artifact frontmatter rewrite.

PC3 (post-review 2026-05-12 Cluster C-J): :func:`Path.write_text` leaves a
truncated artifact on crash mid-write. :func:`atomic_write_text` writes to
a sibling tmp file, fsyncs the bytes, atomically renames via
:func:`os.replace`, then fsyncs the parent directory so the rename's
dir-entry is durable across crash (POSIX-only; Windows skips).

Extracted from `_verify_post.py` (LOC-cap split, post-review 2026-05-12)
so each verify module stays under the Architecture §1052-§1112 /
NFR-MAINT-3 400-LOC cap.

Private CLI-internal — not exported via :mod:`sdlc.cli.verify`.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

__all__ = ("atomic_write_text",)


def atomic_write_text(artifact_path: Path, new_content: str) -> None:
    """Crash-safe write: tmp file in same dir, fsync, os.replace, fsync parent.

    Steps:

      1. Write payload to ``<path>.<rand>.tmp`` in the same directory
         (same-FS guarantee for ``os.replace`` atomicity).
      2. Flush + fsync the tmp file so bytes are durably on disk.
      3. ``os.replace(tmp, artifact_path)`` — atomic rename per POSIX +
         per Windows MoveFileExW with ``MOVEFILE_REPLACE_EXISTING``.
      4. On POSIX, fsync the parent directory so the rename's dir-entry
         is durable across crash. Skipped on Windows (no portable
         directory-fd fsync; ReFS/NTFS handle journaling differently).
    """
    parent = artifact_path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{artifact_path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, artifact_path)
    except BaseException:
        # Best-effort cleanup; do not mask the original exception.
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise

    # POSIX: durably persist the rename's directory entry.
    if sys.platform != "win32":
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            return  # parent unreadable; bytes already persisted by os.replace
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

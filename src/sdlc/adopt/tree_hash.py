"""Pure-Python source-tree hash for NFR-REL-6 (Story 3.7, D4=b).

Captures relpath, mode bits, and symlink target (or file content digest) so
changes invisible to ``git diff`` (mtime, mode, xattr, symlink target) are
still detected. Used from tests and optionally from ``assert_source_untouched``
callers in the test layer.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sdlc.adopt.source_tree import is_source_path


def _entry_fingerprint(root: Path, rel_posix: str) -> str:
    path = root / rel_posix
    st = path.lstat()
    mode = oct(st.st_mode & 0o777777)
    if path.is_symlink():
        target = os.readlink(path)
        body = f"{rel_posix}|symlink|{mode}|{target}"
    else:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        body = f"{rel_posix}|file|{mode}|{digest}"
    return body


def iter_source_relpaths(
    root: Path,
    *,
    legacy_code_globs: tuple[str, ...] = (),
) -> list[str]:
    """Sorted relative posix paths under ``root`` matching the source-tree definition."""
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            abs_path = Path(dirpath) / filename
            rel_posix = abs_path.relative_to(root).as_posix()
            if is_source_path(rel_posix, legacy_code_globs):
                found.append(rel_posix)
    return sorted(found)


def compute_source_tree_hash(
    root: Path,
    *,
    legacy_code_globs: tuple[str, ...] = (),
) -> str:
    """Deterministic sha256 hex digest over the configured source tree."""
    lines = [
        _entry_fingerprint(root, rel)
        for rel in iter_source_relpaths(root, legacy_code_globs=legacy_code_globs)
    ]
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

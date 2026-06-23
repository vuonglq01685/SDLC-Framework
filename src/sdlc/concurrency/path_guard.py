"""Repo-containment guard for clarification/signoff write & unlink callsites.

ADR-037 / Epic-4 retro D1 (CR4.12-W1). ``assert_contained(path, root)``
rejects (raises :class:`~sdlc.errors.SecurityError`, ``ERR_SECURITY``) when:

- the path contains a ``..`` traversal component,
- the path's absolute form is not lexically under ``root`` (absolute escape),
- any component from ``root`` toward the target — ancestor **or** leaf — is a
  symlink (``Path.resolve()`` silently follows symlinks, so the symlink walk runs on the
  *un-resolved* components before the final containment compare; covers Windows reparse
  points via ``Path.is_symlink``).

On success it returns the absolute, symlink-free path to write/unlink. The guard runs at
the callsite (``engine.auto_mad``, ``cli.unsign``, ``dashboard`` static serving) —
``atomic_write``'s ADR-031 contract is unchanged. Reject-outright (no clamp): silently
redirecting a symlink-escaping mutation would hide the attack and can corrupt a legitimate
target. Mirrors the containment patterns in ``adopt/invariant.py`` and
``cli/_verify_paths.py``, generalised to an arbitrary ``root`` and reused across
``engine`` + ``cli`` + ``dashboard``.

Amendment (Story 5.1 / D2): ``assert_contained`` is the canonical primitive;
``assert_repo_contained`` is a thin alias for ``root=repo_root``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, NoReturn

from sdlc.errors import SecurityError

_PARENT_REF: Final[str] = ".."


def _reject(reason: str, *, path: Path, root: Path, extra: object = None) -> NoReturn:
    details: dict[str, object] = {"path": str(path), "root": str(root)}
    if extra is not None:
        details["component"] = str(extra)
    raise SecurityError(reason, details=details)


def assert_contained(path: Path, root: Path) -> Path:
    """Return the safe absolute ``path`` iff contained under ``root``, else raise.

    See module docstring for the rejection rules. The returned path is absolute and
    symlink-free, suitable to hand directly to ``atomic_write``, ``Path.unlink``, or
    static-file serving.
    """
    root_resolved = root.resolve()
    raw = path if path.is_absolute() else (root / path)

    if _PARENT_REF in raw.parts:
        _reject("refusing a path with a '..' traversal component", path=path, root=root)

    try:
        relative = raw.relative_to(root)
    except ValueError:
        _reject("refusing a path outside the containment root", path=path, root=root)

    walk = root
    for part in relative.parts:
        walk = walk / part
        try:
            is_link = walk.is_symlink()
        except OSError:
            _reject("refusing an unstattable path component", path=path, root=root, extra=part)
        if is_link:
            _reject("refusing a symlink path component", path=path, root=root, extra=part)

    resolved = raw.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        _reject(
            "refusing a path that resolves outside the containment root",
            path=path,
            root=root,
        )
    return resolved


def assert_repo_contained(path: Path, repo_root: Path) -> Path:
    """Return the safe absolute ``path`` iff contained under ``repo_root``, else raise."""
    return assert_contained(path, repo_root)

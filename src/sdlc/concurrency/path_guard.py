"""Repo-containment guard for clarification/signoff write & unlink callsites.

ADR-037 / Epic-4 retro D1 (CR4.12-W1). ``assert_repo_contained(path, repo_root)``
rejects (raises :class:`~sdlc.errors.SecurityError`, ``ERR_SECURITY``) when:

- the path contains a ``..`` traversal component,
- the path's absolute form is not lexically under ``repo_root`` (absolute escape),
- any component from ``repo_root`` toward the target — ancestor **or** leaf — is a
  symlink (``Path.resolve()`` silently follows symlinks, so the symlink walk runs on the
  *un-resolved* components before the final containment compare; covers Windows reparse
  points via ``Path.is_symlink``).

On success it returns the absolute, symlink-free path to write/unlink. The guard runs at
the callsite (``engine.auto_mad``, ``cli.unsign``) — ``atomic_write``'s ADR-031 contract is
unchanged. Reject-outright (no clamp): silently redirecting a symlink-escaping mutation
would hide the attack and can corrupt a legitimate target. Mirrors the containment patterns
in ``adopt/invariant.py`` and ``cli/_verify_paths.py``, generalised to an arbitrary
``repo_root`` and reused across ``engine`` + ``cli``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, NoReturn

from sdlc.errors import SecurityError

_PARENT_REF: Final[str] = ".."


def _reject(reason: str, *, path: Path, repo_root: Path, extra: object = None) -> NoReturn:
    details: dict[str, object] = {"path": str(path), "repo_root": str(repo_root)}
    if extra is not None:
        details["component"] = str(extra)
    raise SecurityError(reason, details=details)


def assert_repo_contained(path: Path, repo_root: Path) -> Path:
    """Return the safe absolute ``path`` iff contained under ``repo_root``, else raise.

    See module docstring for the rejection rules. The returned path is absolute and
    symlink-free, suitable to hand directly to ``atomic_write`` or ``Path.unlink``.
    """
    root = repo_root.resolve()
    raw = path if path.is_absolute() else (repo_root / path)

    # 1. Lexical traversal: a `..` could escape repo_root before any symlink is involved.
    if _PARENT_REF in raw.parts:
        _reject("refusing a path with a '..' traversal component", path=path, repo_root=repo_root)

    # 2. Absolute escape: the path must be lexically under repo_root. relative_to() is a
    #    pure-lexical compare here (we have not resolved symlinks yet, by design). _reject is
    #    NoReturn, so `relative` is definitely bound after the except branch.
    try:
        relative = raw.relative_to(repo_root)
    except ValueError:
        _reject("refusing a path outside the repository root", path=path, repo_root=repo_root)

    # 3. Symlink walk on the UN-resolved components: a symlinked ancestor/leaf would let
    #    resolve() follow the link, defeating the post-resolve containment compare.
    walk = repo_root
    for part in relative.parts:
        walk = walk / part
        try:
            is_link = walk.is_symlink()
        except OSError:  # broken link / permission — fail closed
            _reject(
                "refusing an unstattable path component", path=path, repo_root=repo_root, extra=part
            )
        if is_link:
            _reject("refusing a symlink path component", path=path, repo_root=repo_root, extra=part)

    # 4. No symlink components remain → resolve() is now safe and must stay under root.
    resolved = raw.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        _reject(
            "refusing a path that resolves outside the repository root",
            path=path,
            repo_root=repo_root,
        )
    return resolved

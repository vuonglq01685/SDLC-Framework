"""Conflict-resolution filesystem mechanics for Pass 2 (Story 3.6).

Byte-preserving backup of a colliding real file and symlink replace/remove helpers, plus
best-effort compensation (restore) used when a symlink create fails AFTER a destructive step,
so a half-resolved conflict never leaves the slot broken with the user's bytes stranded.
POSIX-only (ADR-034). No ``cli`` imports — prompts live in ``cli/adopt.py``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Final

from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes._symlink import assert_target_under_root
from sdlc.errors import AdoptError

_CONFLICTS_DIR_REL: Final[str] = ".claude/state/adopt-conflicts"


def conflict_backup_dir(root: Path, timestamp: str) -> Path:
    """Absolute directory for one conflict backup batch, guarded under ``.claude/``."""
    dest = (root / _CONFLICTS_DIR_REL / timestamp).resolve()
    assert_path_under_claude(root, dest)
    return dest


def _unique_backup_path(backup_dir: Path, name: str) -> Path:
    """A non-colliding ``<name>.bak`` path inside ``backup_dir`` (DN1 option b).

    Two distinct real files sharing a basename and backed up in the same millisecond batch
    would otherwise clobber each other's ``.bak`` (the D5(a) residual gap). A numeric suffix
    keeps every backup byte-preserving.
    """
    candidate = backup_dir / f"{name}.bak"
    counter = 1
    while candidate.exists():
        candidate = backup_dir / f"{name}.{counter}.bak"
        counter += 1
    return candidate


def backup_real_file(root: Path, target_rel: str, *, timestamp: str) -> Path:
    """Move the real file at ``target_rel`` to ``adopt-conflicts/<ts>/<basename>.bak``.

    The move is byte-preserving (rename when possible, copy+unlink across filesystems). Any
    ``OSError`` (unwritable backup dir, cross-fs copy failure, …) is wrapped into ``AdoptError``
    so the caller's per-artifact fail-soft boundary holds instead of aborting the whole pass.
    """
    target_abs = assert_target_under_root(root, target_rel)
    if target_abs.is_symlink() or not target_abs.is_file():
        raise AdoptError(
            "adopt conflict backup requires a real file at the target",
            details={"target": target_rel},
        )
    backup_dir = conflict_backup_dir(root, timestamp)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = _unique_backup_path(backup_dir, target_abs.name)
        try:
            os.replace(target_abs, backup_path)
        except OSError:
            shutil.copy2(target_abs, backup_path)
            target_abs.unlink()
    except OSError as exc:
        raise AdoptError(
            "adopt could not back up the conflicting real file",
            details={"target": target_rel, "cause": str(exc)},
        ) from exc
    return backup_path


def restore_real_file(root: Path, target_rel: str, backup_path: Path) -> bool:
    """Best-effort move a backed-up real file back to its slot (compensation).

    Used when the symlink create fails AFTER a backup: the user's file must not be left only in
    the hidden backup dir while the slot reports a skip. Returns True iff it was restored; on
    failure the bytes still survive in ``backup_path`` (the caller warns with that path).
    """
    target_abs = assert_target_under_root(root, target_rel)
    if target_abs.is_symlink() or target_abs.exists():
        return False
    try:
        try:
            os.replace(backup_path, target_abs)
        except OSError:
            shutil.copy2(backup_path, target_abs)
            backup_path.unlink()
    except OSError:
        return False
    return True


def remove_symlink_at_target(root: Path, target_rel: str) -> str | None:
    """Remove an existing symlink at ``target_rel``; return its raw link text.

    Returns None when ``target_rel`` is not a symlink (no-op). The raw link text lets the caller
    restore the exact link verbatim if a subsequent create fails.
    """
    target_abs = assert_target_under_root(root, target_rel)
    if not target_abs.is_symlink():
        return None
    try:
        raw = os.readlink(target_abs)
        os.unlink(target_abs)  # os.unlink (not Path.unlink) — consistent with os.readlink
    except OSError as exc:
        raise AdoptError(
            "adopt could not remove the conflicting symlink at the target",
            details={"target": target_rel, "cause": str(exc)},
        ) from exc
    return raw


def restore_symlink(root: Path, target_rel: str, link_text: str) -> None:
    """Best-effort re-create a removed symlink (compensation on a failed replace)."""
    target_abs = assert_target_under_root(root, target_rel)
    if target_abs.is_symlink() or target_abs.exists():
        return
    try:
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link_text, target_abs)
    except OSError:
        pass


def read_other_symlink_source_rel(root: Path, target_rel: str) -> str:
    """Repo-relative path the existing symlink at ``target_rel`` currently points at.

    A dangling or out-of-root link is reported via its RAW link text (not a ``..``-escaping /
    canonicalised absolute path), so an external path never leaks into the conflict prompt or
    the ``symlink_replaced`` audit payload.
    """
    target_abs = assert_target_under_root(root, target_rel)
    if not target_abs.is_symlink():
        raise AdoptError(
            "adopt expected a symlink at the target for conflict resolution",
            details={"target": target_rel},
        )
    try:
        raw = os.readlink(target_abs)
    except OSError as exc:
        raise AdoptError(
            "adopt could not read an existing symlink at the target",
            details={"target": target_rel, "cause": str(exc)},
        ) from exc
    resolved = (target_abs.parent / raw).resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or root_resolved in resolved.parents:
        return os.path.relpath(resolved, start=root_resolved)
    return raw

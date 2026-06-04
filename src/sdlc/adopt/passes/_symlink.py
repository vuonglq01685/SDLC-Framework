"""Relative-symlink filesystem helper for Pass 2 (Story 3.3, D4(a) — under `passes/`).

Pure filesystem mechanics, separated from the offer/decision logic in `symlink_offer.py`
to keep each file focused (NFR-MAINT-3, ≤400 LOC). POSIX-only (ADR-034): `os.symlink` with
a `os.path.relpath` link text so the canonical slot points back at the pre-existing source
with a repo-relative link (survives a repo move; epics.md:1827).

The symlink TARGET (a canonical SDLC slot, e.g. `02-Architecture/02-System/ARCHITECTURE.md`)
lives in the project root, OUTSIDE `.claude/` — this is the one sanctioned write outside
`.claude/` in adopt mode. `assert_target_under_root` is the defence-in-depth guard ensuring
an edited target (D3) cannot escape the project root via `..`/absolute paths.

Boundary (scripts/module_boundary_table.py): `adopt/` MUST NOT import `cli`/`engine`/
`dispatcher`/`runtime`. This module imports only stdlib + `sdlc.errors`.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from sdlc.errors import AdoptError


class SymlinkOutcome(Enum):
    """Result of attempting to create one adopt symlink at a canonical target."""

    CREATED = "created"  # a new relative symlink was created
    ALREADY_CORRECT = "already_correct"  # target already a symlink pointing at this source (AC4)
    CONFLICT = "conflict"  # a real file or a symlink elsewhere occupies the target (AC4 → 3.6)
    SOURCE_MISSING = "source_missing"  # source no longer resolves to a real file → no broken link


def resolve_target(suggested_target: str, source_rel: str) -> str:
    """Resolve a `suggested_target` to a concrete file path (repo-relative POSIX).

    A directory-style slot (trailing ``/``, e.g. research's ``01-Requirement/02-Research/``)
    has the source's basename appended so the symlink lands at a file, not the directory.
    """
    if suggested_target.endswith("/"):
        return suggested_target + Path(source_rel).name
    return suggested_target


def is_target_under_root(root: Path, target_rel: str) -> bool:
    """True iff ``target_rel`` is a non-empty relative path resolving at/under ``root``.

    The single shared "stays under root" predicate (D3 edit validation): both the `cli` edit
    guard and the `adopt/` core re-validate the (possibly injected) target through this, so the
    two layers cannot drift. Rejects empty/whitespace-only, absolute, and `..`-escaping targets.
    """
    if not target_rel.strip() or os.path.isabs(target_rel):
        return False
    root_resolved = root.resolve()
    target_abs = (root / target_rel).resolve()
    return target_abs == root_resolved or root_resolved in target_abs.parents


def assert_target_under_root(root: Path, target_rel: str) -> Path:
    """Return the absolute target path, or raise ``AdoptError`` if it escapes ``root``.

    Defence-in-depth backstop over :func:`is_target_under_root`: the one sanctioned write
    outside `.claude/` (the symlink target) must never let adopt write outside the project root
    via an empty/absolute/`..`-escaping target (D3).
    """
    if not is_target_under_root(root, target_rel):
        raise AdoptError(
            "adopt refuses a symlink target outside the project root",
            details={"target": target_rel, "root": str(root)},
        )
    return root / target_rel


def create_relative_symlink(root: Path, source_rel: str, target_rel: str) -> SymlinkOutcome:
    """Create a relative symlink at ``target_rel`` pointing back at ``source_rel``.

    Both paths are repo-relative POSIX. Never clobbers an existing path and never creates a
    broken link:
      * source no longer resolves to a real file (deleted between Pass 1/2, or a dangling
        symlink) → ``SOURCE_MISSING`` (do not symlink to nothing);
      * target is already a symlink pointing at ``source_rel`` → ``ALREADY_CORRECT`` (idempotent);
      * target is any other existing path (real file, or symlink elsewhere) → ``CONFLICT``;
      * otherwise the parent dirs are created and a relative symlink is written → ``CREATED``.

    `OSError` from the filesystem is wrapped into a typed `AdoptError` (no raw traceback).
    """
    target_abs = assert_target_under_root(root, target_rel)
    source_abs = root / source_rel

    if not source_abs.exists():  # source gone since Pass 1, or itself a dangling symlink
        return SymlinkOutcome.SOURCE_MISSING

    if target_abs.is_symlink():
        try:
            current = (target_abs.parent / os.readlink(target_abs)).resolve()
        except OSError as exc:  # unreadable link → treat as conflict, do not clobber
            raise AdoptError(
                "adopt could not read an existing symlink at the target",
                details={"target": target_rel, "cause": str(exc)},
            ) from exc
        if current == source_abs.resolve():
            return SymlinkOutcome.ALREADY_CORRECT
        return SymlinkOutcome.CONFLICT
    if target_abs.exists():  # a real file or directory occupies the slot
        return SymlinkOutcome.CONFLICT

    link_text = os.path.relpath(source_abs, start=target_abs.parent)
    try:
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link_text, target_abs)
    except OSError as exc:
        raise AdoptError(
            "adopt could not create the symlink",
            details={"target": target_rel, "source": source_rel, "cause": str(exc)},
        ) from exc
    return SymlinkOutcome.CREATED

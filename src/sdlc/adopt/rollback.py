"""Adopt rollback core — remove tracked symlinks and prune the manifest (Story 3.5).

Reverses Pass 2/3 symlink adoption using the frozen ``adopted-symlinks.json`` manifest.
Symlink removal + manifest rewrite + ``symlink_rolled_back`` journal events live here;
orphan-signoff detection and ``--force`` invalidation are orchestrated from ``cli/``
(``adopt/`` must not import ``engine`` per module boundaries).

Per mapping the order is: reconcile/unlink the slot → append journal event(s) → rewrite
the manifest once after the loop. The journal is the audit source of truth; the manifest
is a derived cache (a mid-loop crash may leave the manifest lagging until a re-run — AC4
idempotency converges on retry).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sdlc.adopt.imported_metadata import metadata_record_path
from sdlc.adopt.passes._symlink import is_target_under_root
from sdlc.adopt.passes.symlink_offer import (
    _load_existing_mappings,
    _write_manifest,
)
from sdlc.contracts.adopted_symlinks import SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import allocate_next_seq_for_append_sync, append_sync

_KIND_ROLLED_BACK: Final[str] = "symlink_rolled_back"
_ACTOR: Final[str] = "cli"
_TARGET_ID: Final[str] = "adopt"
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64

WarnCallback = Callable[[str], None]


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of a rollback run."""

    removed_targets: tuple[str, ...]


def _warn(warn: WarnCallback | None, message: str) -> None:
    if warn is not None:
        warn(message)


def _select_mappings(
    mappings: list[SymlinkMapping],
    targets: Sequence[str] | None,
) -> list[SymlinkMapping]:
    if targets is None:
        return list(mappings)
    target_set = frozenset(targets)
    selected = [m for m in mappings if m.target in target_set]
    found = {m.target for m in selected}
    missing = sorted(target_set - found)
    if missing:
        raise AdoptError(
            "rollback target is not in adopted-symlinks manifest",
            details={"target": missing[0], "missing": missing},
        )
    return selected


def _prune_sidecar(root: Path, target: str, *, warn: WarnCallback | None) -> None:
    path = metadata_record_path(root, target)
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        _warn(warn, f"could not delete imported-metadata sidecar for {target}: {exc}")


def _reconcile_and_unlink(
    root: Path,
    mapping: SymlinkMapping,
    *,
    warn: WarnCallback | None,
) -> None:
    """Remove the adopt symlink at ``mapping.target`` when safe; never touch ``mapping.source``."""
    # Defense-in-depth: SymlinkMapping.target is an unvalidated str, so a tampered manifest
    # could carry an absolute / ``..``-escaping target. Re-validate through the shared
    # predicate before touching disk (AC5: writes touch ONLY the link node + .claude/).
    if not is_target_under_root(root, mapping.target):
        _warn(warn, f"{mapping.target} escapes the project root; leaving on-disk path untouched")
        return
    slot = root / mapping.target
    source_abs = (root / mapping.source).resolve()

    if not os.path.lexists(slot):
        _warn(warn, f"symlink at {mapping.target} already removed; pruning manifest entry")
        return

    if slot.is_symlink():
        try:
            current = (slot.parent / os.readlink(slot)).resolve()
        except OSError:
            slot.unlink()
            _warn(warn, f"removed dangling symlink at {mapping.target}")
            return
        if current == source_abs:
            slot.unlink()
            return
        _warn(
            warn,
            f"{mapping.target} is a symlink but no longer points at {mapping.source}; "
            "leaving on-disk link untouched",
        )
        return

    if slot.exists():
        _warn(
            warn,
            f"{mapping.target} is no longer an adopt symlink; leaving on-disk file untouched",
        )


def _append_rollback_event(journal_path: Path, *, payload: dict[str, object]) -> None:
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=now_rfc3339_utc_ms(),
        actor=_ACTOR,
        kind=_KIND_ROLLED_BACK,
        target_id=_TARGET_ID,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload=payload,
    )
    append_sync(entry, journal_path=journal_path)


def rollback(
    root: Path,
    *,
    targets: Sequence[str] | None,
    journal_path: Path,
    warn: WarnCallback | None = None,
) -> RollbackResult:
    """Roll back adopt symlinks for ``targets``, or all mappings when ``targets`` is None."""
    all_mappings = _load_existing_mappings(root, warn=warn)
    to_remove = _select_mappings(all_mappings, targets)
    if not to_remove:
        return RollbackResult(removed_targets=())

    removed: list[str] = []
    for mapping in to_remove:
        _reconcile_and_unlink(root, mapping, warn=warn)
        _prune_sidecar(root, mapping.target, warn=warn)
        removed.append(mapping.target)

    if targets is None or len(to_remove) > 1:
        _append_rollback_event(
            journal_path,
            payload={
                "count": len(to_remove),
                "targets": [m.target for m in to_remove],
            },
        )
    else:
        mapping = to_remove[0]
        _append_rollback_event(
            journal_path,
            payload={"target": mapping.target, "source": mapping.source},
        )

    remaining = [m for m in all_mappings if m.target not in frozenset(removed)]
    _write_manifest(root, remaining)
    return RollbackResult(removed_targets=tuple(removed))

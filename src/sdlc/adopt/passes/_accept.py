"""Per-artifact accept + conflict-resolution orchestration for Pass 2 (Story 3.3 + 3.6).

Split out of ``symlink_offer.py`` to keep each module ≤400 LOC (NFR-MAINT-3). The offer LOOP
(threshold gating, manifest flush) lives in ``symlink_offer``; this module decides ONE artifact:
create-or-conflict, the real-file ``[s/b/d]`` and different-symlink ``[s/r/d]`` flows, and the
per-symlink journal events. POSIX-only (ADR-034); no ``cli`` import (the boundary holds).

A destructive conflict step (backup-move / old-symlink removal) is coupled with the symlink
create so a create-failure compensates immediately (restore the ``.bak`` / re-create the old
link) — never leaving the slot broken or the user's bytes stranded.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from sdlc.adopt.passes._conflict import (
    backup_real_file,
    read_other_symlink_source_rel,
    remove_symlink_at_target,
    restore_real_file,
    restore_symlink,
)
from sdlc.adopt.passes._symlink import (
    SymlinkOutcome,
    create_relative_symlink,
    is_target_under_root,
    resolve_target,
)
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import allocate_next_seq_for_append_sync, append_sync

_KIND_SYMLINK_ACCEPTED: Final[str] = "symlink_accepted"
_KIND_SYMLINK_REPLACED: Final[str] = "symlink_replaced"
_KIND_ADOPT_RE_RUN: Final[str] = "adopt_re_run"
_ACTOR: Final[str] = "cli"
_TARGET_ID: Final[str] = "adopt"
# Event-only entries record no content write → all-zero sha256 sentinel (ADR-028 §2).
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64
_MAX_DIFFERENT_TARGET_ATTEMPTS: Final[int] = 8

# The injected human-warning sink (routes through `cli/output`; no-op when un-injected).
WarnCallback = Callable[[str], None]


class ConflictKind(Enum):
    REAL_FILE = "real_file"
    OTHER_SYMLINK = "other_symlink"


@dataclass(frozen=True)
class ConflictContext:
    kind: ConflictKind
    other_source: str | None = None


@dataclass(frozen=True)
class ConflictDecision:
    action: Literal["skip", "backup_replace", "replace", "different_target"]
    target: str = ""


# The injected conflict-resolution prompt (built by `cli`): decide skip / backup_replace /
# replace / different_target for one colliding canonical slot.
ConflictCallback = Callable[[DetectedArtifact, str, ConflictContext], ConflictDecision]


def _append_journal_event(
    journal_path: Path, *, kind: str, ts: str, payload: dict[str, object]
) -> None:
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=_ACTOR,
        kind=kind,
        target_id=_TARGET_ID,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload=payload,
    )
    append_sync(entry, journal_path=journal_path)


def _append_symlink_event(journal_path: Path, mapping: SymlinkMapping) -> None:
    _append_journal_event(
        journal_path,
        kind=_KIND_SYMLINK_ACCEPTED,
        ts=mapping.accepted_at,
        payload={"source": mapping.source, "target": mapping.target, "kind": mapping.kind},
    )


def _append_symlink_replaced_event(
    journal_path: Path, *, target: str, old_source: str, ts: str
) -> None:
    _append_journal_event(
        journal_path,
        kind=_KIND_SYMLINK_REPLACED,
        ts=ts,
        payload={"target": target, "old_source": old_source},
    )


def append_adopt_rerun_event(
    journal_path: Path, *, new_adoptions: int, skipped_existing: int, ts: str
) -> None:
    """Append the per-re-run ``adopt_re_run`` summary event (D3; called by the offer loop)."""
    _append_journal_event(
        journal_path,
        kind=_KIND_ADOPT_RE_RUN,
        ts=ts,
        payload={"new_adoptions": new_adoptions, "skipped_existing": skipped_existing},
    )


_SKIP_REASON_BY_OUTCOME: Final[dict[SymlinkOutcome, str]] = {
    SymlinkOutcome.SOURCE_MISSING: "source no longer exists (no symlink created)",
    SymlinkOutcome.CONFLICT_REAL_FILE: "target already exists as a real file",
    SymlinkOutcome.CONFLICT_OTHER_SYMLINK: "target already occupied by a different symlink",
}


def _warn_skip(path: str, reason: str, *, warn: WarnCallback | None) -> None:
    if warn is not None:
        warn(f"skipping {path}: {reason}")


def _outcome_for_target(
    root: Path, artifact: DetectedArtifact, target_rel: str
) -> SymlinkOutcome | AdoptError:
    if not is_target_under_root(root, target_rel):
        return AdoptError(
            "adopt refuses a symlink target outside the project root",
            details={"target": target_rel},
        )
    try:
        return create_relative_symlink(root, artifact.path, target_rel)
    except AdoptError as exc:
        return exc


def _record_accepted_mapping(
    artifact: DetectedArtifact,
    final_target: str,
    mappings: list[SymlinkMapping],
    recorded_targets: set[str],
    *,
    journal_path: Path | None,
    accepted_at: str | None = None,
) -> None:
    """Append the accepted mapping + journal `symlink_accepted`.

    `accepted_at` is sampled by the caller on a conflict-replace path so the paired
    `symlink_replaced` event and this mapping share ONE timestamp (the inherited 3.4
    single-timestamp cross-reference invariant); otherwise it is sampled here.
    """
    mapping = SymlinkMapping(
        source=artifact.path,
        target=final_target,
        accepted_at=accepted_at or now_rfc3339_utc_ms(),
        kind=artifact.kind,
    )
    if journal_path is not None:
        _append_symlink_event(journal_path, mapping)
    mappings.append(mapping)
    recorded_targets.add(final_target)


def _do_backup_replace(
    root: Path,
    artifact: DetectedArtifact,
    target_rel: str,
    mappings: list[SymlinkMapping],
    recorded_targets: set[str],
    *,
    journal_path: Path | None,
    warn: WarnCallback | None,
) -> bool:
    """Backup the colliding real file, THEN create the symlink (AC2 `b`).

    The destructive backup and the create are coupled here so a create-failure compensates
    immediately: the backed-up file is moved back to its slot rather than stranded in the
    hidden conflict dir while the slot reports a skip (never silent data loss).
    """
    ts = now_rfc3339_utc_ms()
    try:
        backup_path = backup_real_file(root, target_rel, timestamp=ts)
    except AdoptError as exc:
        _warn_skip(artifact.path, exc.message, warn=warn)
        return False
    created = _outcome_for_target(root, artifact, target_rel)
    if created in (SymlinkOutcome.CREATED, SymlinkOutcome.ALREADY_CORRECT):
        _record_accepted_mapping(
            artifact,
            target_rel,
            mappings,
            recorded_targets,
            journal_path=journal_path,
            accepted_at=ts,
        )
        return True
    if restore_real_file(root, target_rel, backup_path):
        _warn_skip(artifact.path, "create after backup failed; original file restored", warn=warn)
    else:
        _warn_skip(
            artifact.path,
            f"create after backup failed; original file preserved at {backup_path}",
            warn=warn,
        )
    return False


def _do_replace(
    root: Path,
    artifact: DetectedArtifact,
    target_rel: str,
    old_source: str | None,
    mappings: list[SymlinkMapping],
    recorded_targets: set[str],
    *,
    journal_path: Path | None,
    warn: WarnCallback | None,
) -> bool:
    """Remove the different symlink, THEN create the new one (AC3 `r`).

    Order mirrors 3.3's create→journal→record: the old link is removed, the new link created,
    and ONLY on success are the paired `symlink_replaced` (old removal) + `symlink_accepted`
    (new mapping) journaled — both with the SAME `ts`. A create-failure restores the previous
    link verbatim (no broken/empty slot, no orphan removal event).
    """
    ts = now_rfc3339_utc_ms()
    try:
        removed_link = remove_symlink_at_target(root, target_rel)
    except AdoptError as exc:
        _warn_skip(artifact.path, exc.message, warn=warn)
        return False
    created = _outcome_for_target(root, artifact, target_rel)
    if created in (SymlinkOutcome.CREATED, SymlinkOutcome.ALREADY_CORRECT):
        if journal_path is not None and old_source is not None:
            _append_symlink_replaced_event(
                journal_path, target=target_rel, old_source=old_source, ts=ts
            )
        _record_accepted_mapping(
            artifact,
            target_rel,
            mappings,
            recorded_targets,
            journal_path=journal_path,
            accepted_at=ts,
        )
        return True
    if removed_link is not None:
        restore_symlink(root, target_rel, removed_link)
    _warn_skip(
        artifact.path, "create after symlink-replace failed; previous symlink restored", warn=warn
    )
    return False


def accept_one_artifact(  # noqa: C901, PLR0911, PLR0912
    root: Path,
    artifact: DetectedArtifact,
    initial_target: str,
    mappings: list[SymlinkMapping],
    recorded_targets: set[str],
    *,
    journal_path: Path | None,
    conflict: ConflictCallback | None,
    warn: WarnCallback | None,
) -> bool:
    """Create-or-resolve ONE artifact's symlink; return True iff a mapping was recorded."""
    target_rel = initial_target
    # Bound ONLY the `[d]`ifferent-target re-prompts (a `b`/`r` resolves in one shot, so it must
    # not consume the budget — P9). An unsafe/colliding `d` answer re-prompts (bounded) instead
    # of silently skipping.
    different_target_attempts = 0

    while True:
        if target_rel in recorded_targets:
            return False

        outcome = _outcome_for_target(root, artifact, target_rel)
        if isinstance(outcome, AdoptError):
            if "outside the project root" in outcome.message:
                _warn_skip(
                    artifact.path, f"unsafe target {target_rel!r} escapes project root", warn=warn
                )
            else:
                _warn_skip(artifact.path, outcome.message, warn=warn)
            return False

        if outcome in (SymlinkOutcome.CREATED, SymlinkOutcome.ALREADY_CORRECT):
            _record_accepted_mapping(
                artifact, target_rel, mappings, recorded_targets, journal_path=journal_path
            )
            return True

        if outcome == SymlinkOutcome.SOURCE_MISSING:
            _warn_skip(artifact.path, _SKIP_REASON_BY_OUTCOME[outcome], warn=warn)
            return False

        if outcome not in (
            SymlinkOutcome.CONFLICT_REAL_FILE,
            SymlinkOutcome.CONFLICT_OTHER_SYMLINK,
        ):
            _warn_skip(artifact.path, f"unexpected symlink outcome {outcome!r}", warn=warn)
            return False

        if conflict is None:
            _warn_skip(artifact.path, _SKIP_REASON_BY_OUTCOME[outcome], warn=warn)
            return False

        if outcome == SymlinkOutcome.CONFLICT_REAL_FILE:
            ctx = ConflictContext(kind=ConflictKind.REAL_FILE)
        else:
            try:
                other = read_other_symlink_source_rel(root, target_rel)
            except AdoptError as exc:
                _warn_skip(artifact.path, exc.message, warn=warn)
                return False
            ctx = ConflictContext(kind=ConflictKind.OTHER_SYMLINK, other_source=other)

        decision = conflict(artifact, target_rel, ctx)

        if decision.action == "skip":
            return False

        if decision.action == "different_target":
            if different_target_attempts >= _MAX_DIFFERENT_TARGET_ATTEMPTS:
                _warn_skip(artifact.path, "too many different-target attempts; skipping", warn=warn)
                return False
            different_target_attempts += 1
            new_target = resolve_target(decision.target, artifact.path)
            if not is_target_under_root(root, new_target):
                _warn_skip(
                    artifact.path,
                    f"unsafe target {new_target!r} escapes project root; re-prompting",
                    warn=warn,
                )
                continue
            target_rel = new_target
            continue

        if decision.action == "backup_replace":
            if outcome != SymlinkOutcome.CONFLICT_REAL_FILE:
                _warn_skip(
                    artifact.path,
                    "backup-and-replace is only valid for a real-file conflict",
                    warn=warn,
                )
                return False
            return _do_backup_replace(
                root,
                artifact,
                target_rel,
                mappings,
                recorded_targets,
                journal_path=journal_path,
                warn=warn,
            )

        # The only remaining action is "replace" (the Literal is exhaustively narrowed).
        if outcome != SymlinkOutcome.CONFLICT_OTHER_SYMLINK:
            _warn_skip(
                artifact.path,
                "replace is only valid for a different-symlink conflict",
                warn=warn,
            )
            return False
        return _do_replace(
            root,
            artifact,
            target_rel,
            ctx.other_source,
            mappings,
            recorded_targets,
            journal_path=journal_path,
            warn=warn,
        )

"""Pass 2 — offer to symlink detected artifacts into the canonical layout (Story 3.3).

`offer_symlinks` walks the frozen `detected[]` Pass 1 produced and, for each offerable artifact
(non-empty `suggested_target`) at or above the integer `auto_accept_threshold`, creates a
relative symlink from the canonical SDLC slot to the pre-existing source (POSIX-only, ADR-034),
records every accepted mapping in `.claude/state/adopted-symlinks.json` (the 7th frozen
wire-format contract), and journals a `symlink_accepted` event per symlink.

The pure core DECIDES (threshold gating, conflict handling, recording); the `cli` layer PROMPTS.
Interactivity, the threshold, and a warning sink are dependency-injected from `cli/adopt.py`
(mirroring Story 3.2's `git_signal` DI) so `adopt/` keeps its boundary: NO `cli`/`engine`/
`dispatcher`/`runtime` import, and no `print` (human output goes through `cli/output`).

  * confirm is not None  ⇒ interactive: ≥ threshold → prompt `[Y/n/edit]`; below → silent skip.
  * confirm is None      ⇒ non-interactive: ≥ threshold → auto-accept; below → skip + warn.

Source files are never modified (NFR-REL-6): the only writes are the symlinks at canonical
target paths (outside `.claude/`, the one sanctioned exception) and the manifest + journal
(under `.claude/`, pre-guarded by `assert_path_under_claude`).

Per accepted symlink the order is: create the symlink → append the `symlink_accepted` journal
event → record the mapping; the manifest is flushed ONCE after the loop. The journal is the
audit source of truth (Story 3.5 rollback / 3.6 idempotency rebuild from it), and the manifest
is a derived cache. Each artifact is handled fail-soft: an unsafe target, a missing source, a
target conflict, or an OSError skips that one artifact (with a warning) and never aborts the pass.
Full crash-recovery (reconciling an orphan symlink left by a mid-loop crash) is owned by 3.5/3.6.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes._symlink import (
    SymlinkOutcome,
    create_relative_symlink,
    is_target_under_root,
    resolve_target,
)
from sdlc.concurrency.io_primitives import atomic_write_bytes
from sdlc.config.project import DEFAULT_AUTO_ACCEPT_THRESHOLD
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import allocate_next_seq_for_append_sync, append_sync

_MANIFEST_REL: Final[str] = ".claude/state/adopted-symlinks.json"
_KIND_SYMLINK_ACCEPTED: Final[str] = "symlink_accepted"
_ACTOR: Final[str] = "cli"
_TARGET_ID: Final[str] = "adopt"
# Event-only entries record no content write → all-zero sha256 sentinel (ADR-028 §2).
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64


@dataclass(frozen=True)
class SymlinkDecision:
    """Outcome of an interactive `[Y/n/edit]` offer for one candidate (the `cli` layer builds it).

    `target` is the (possibly edited, D3) repo-relative POSIX slot to symlink into; it is only
    honoured when `accept` is True.
    """

    accept: bool
    target: str


# The injected interactive prompt: given the artifact + its suggested target, decide.
ConfirmCallback = Callable[[DetectedArtifact, str], SymlinkDecision]
# The injected human-warning sink (routes through `cli/output`; no-op when un-injected).
WarnCallback = Callable[[str], None]


def _manifest_bytes(manifest: AdoptedSymlinks) -> bytes:
    """Canonical bytes for `adopted-symlinks.json` — identical scheme to `driver._report_bytes`."""
    text = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _load_existing_mappings(
    root: Path, *, warn: WarnCallback | None = None
) -> list[SymlinkMapping]:
    """Return any prior manifest's mappings (preserved across resume/idempotency), or [].

    A corrupt/unreadable prior manifest must not crash Pass 2 — but it is NOT swallowed
    silently: a warning is surfaced (the journal remains the audit source of truth that 3.5
    rollback and 3.6 idempotency rebuild from, so the manifest is a derived cache we can rebuild).
    """
    manifest_path = root / _MANIFEST_REL
    if not manifest_path.exists():
        return []
    try:
        return list(
            AdoptedSymlinks.model_validate_json(manifest_path.read_text(encoding="utf-8")).mappings
        )
    except (OSError, ValueError) as exc:
        if warn is not None:
            warn(
                f"existing {_MANIFEST_REL} is unreadable ({exc}); starting from an empty manifest "
                "(prior mappings remain recoverable from the journal)"
            )
        return []


def _write_manifest(root: Path, mappings: Sequence[SymlinkMapping]) -> None:
    """Atomically (re)write the manifest, pre-guarded to stay under `.claude/` (AC6)."""
    manifest_path = (root / _MANIFEST_REL).resolve()
    assert_path_under_claude(root, manifest_path)
    atomic_write_bytes(manifest_path, _manifest_bytes(AdoptedSymlinks(mappings=tuple(mappings))))


def _append_symlink_event(journal_path: Path, mapping: SymlinkMapping) -> None:
    """Append a `symlink_accepted` event (mirrors `driver._append_event` — the driver imports
    this module, so the helper is duplicated here rather than coupling `passes/` back to it).

    Reuses ``mapping.accepted_at`` as the journal ``ts`` so the manifest record and the journal
    event for one symlink carry the SAME timestamp (cross-referenceable during 3.5/3.6 audit).
    """
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=mapping.accepted_at,
        actor=_ACTOR,
        kind=_KIND_SYMLINK_ACCEPTED,
        target_id=_TARGET_ID,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload={"source": mapping.source, "target": mapping.target, "kind": mapping.kind},
    )
    append_sync(entry, journal_path=journal_path)


def _select_target(
    artifact: DetectedArtifact,
    *,
    confirm: ConfirmCallback | None,
    auto_accept_threshold: int,
    warn: WarnCallback | None,
) -> str | None:
    """Decide the final (resolved) target to symlink for one artifact, or None to skip.

    Applies, in order: detect-only filter (empty `suggested_target`), the integer threshold gate
    (below ⇒ silent skip interactive / warned skip non-interactive), and the interactive
    `[Y/n/edit]` decision (non-interactive ⇒ auto-accept). The returned path is `resolve_target`-d
    (directory-style slots get the source basename appended).
    """
    if not artifact.suggested_target:
        return None  # detect-only kind (Story 3.2 D1) — never offered
    if artifact.confidence < auto_accept_threshold:
        if confirm is None and warn is not None:  # non-interactive below threshold → warn (AC3)
            warn(
                f"skipping {artifact.path} ({artifact.kind}, confidence "
                f"{artifact.confidence}) — below auto-accept threshold {auto_accept_threshold}"
            )
        return None  # interactive: silent skip (AC1/D1)
    if confirm is None:
        return resolve_target(artifact.suggested_target, artifact.path)  # auto-accept
    decision = confirm(artifact, artifact.suggested_target)
    if not decision.accept:
        return None  # interactive `n` (or unrecognized) — no symlink, no record
    return resolve_target(decision.target, artifact.path)


# Non-fatal outcomes that skip one artifact carry a human skip-reason; CREATED/ALREADY_CORRECT
# are absent (they are recorded, not skipped).
_SKIP_REASON_BY_OUTCOME: Final[dict[SymlinkOutcome, str]] = {
    SymlinkOutcome.SOURCE_MISSING: "source no longer exists (no symlink created)",
    SymlinkOutcome.CONFLICT: (
        "target already exists (conflict resolution deferred to `sdlc adopt` Story 3.6)"
    ),
}


def _create_for_record(
    root: Path, artifact: DetectedArtifact, final_target: str, *, warn: WarnCallback | None
) -> bool:
    """Validate + create the symlink for one artifact; return True iff it should be recorded.

    Fail-soft: an unsafe (escaping) target, a missing source, a target conflict, or an OSError
    each warns and returns False (skip THIS artifact) instead of raising — so one bad artifact
    never aborts the whole pass. Returns True only for `CREATED`/`ALREADY_CORRECT` (AC4).
    """
    reason: str | None
    # Core re-validation of the (possibly injected/edited) target — defence-in-depth shared with
    # the cli edit guard so the two layers cannot disagree.
    if not is_target_under_root(root, final_target):
        reason = f"unsafe target {final_target!r} escapes project root"
    else:
        try:
            outcome = create_relative_symlink(root, artifact.path, final_target)
        except AdoptError as exc:
            reason = exc.message
        else:
            reason = _SKIP_REASON_BY_OUTCOME.get(outcome)
    if reason is None:
        return True  # CREATED or ALREADY_CORRECT (idempotent)
    if warn is not None:
        warn(f"skipping {artifact.path}: {reason}")
    return False


def offer_symlinks(
    root: Path,
    detected: Sequence[DetectedArtifact],
    *,
    confirm: ConfirmCallback | None = None,
    auto_accept_threshold: int = DEFAULT_AUTO_ACCEPT_THRESHOLD,
    warn: WarnCallback | None = None,
    journal_path: Path | None = None,
) -> None:
    """Offer + create symlinks for `detected` artifacts (Story 3.3 implements; 3.1 was a no-op).

    Args:
        root: repository root.
        detected: frozen Pass 1 output (read-only); only non-empty-`suggested_target` artifacts
            are offerable (detect-only kinds carry an empty target per Story 3.2 D1).
        confirm: interactive `[Y/n/edit]` callback (injected by `cli`); None ⇒ non-interactive.
        auto_accept_threshold: integer-percent confidence gate (D1). ≥ ⇒ offer/accept; below ⇒
            silent skip (interactive) or skip+warn (non-interactive).
        warn: human-warning sink (injected by `cli`, routes through `cli/output`); None ⇒ drop.
        journal_path: where to append `symlink_accepted` events; None ⇒ no journaling (resume /
            non-adopt no-op default, so 3.1's orchestrator-ordering test stays unaffected).
    """
    mappings: list[SymlinkMapping] = _load_existing_mappings(root, warn=warn)
    recorded_targets: set[str] = {m.target for m in mappings}
    changed = False

    for artifact in detected:
        final_target = _select_target(
            artifact, confirm=confirm, auto_accept_threshold=auto_accept_threshold, warn=warn
        )
        if final_target is None:
            continue
        # Prior-run idempotency AND duplicate-within-this-run collapse to the same slot → skip
        # before touching the filesystem (no redundant symlink attempt, no misframed conflict).
        if final_target in recorded_targets:
            continue
        # Fail-soft per-artifact validate + create (an unsafe target / missing source / conflict /
        # OSError warns and skips this one, never aborting the pass).
        if not _create_for_record(root, artifact, final_target, warn=warn):
            continue

        # CREATED or ALREADY_CORRECT (idempotent) → record (AC4). One timestamp is sampled and
        # reused for the manifest record AND the journal event. The journal entry is appended
        # BEFORE the manifest is (re)written: the journal is the audit source of truth (3.5/3.6
        # rebuild from it), and the manifest is a derived cache flushed once after the loop.
        mapping = SymlinkMapping(
            source=artifact.path,
            target=final_target,
            accepted_at=now_rfc3339_utc_ms(),
            kind=artifact.kind,
        )
        if journal_path is not None:
            _append_symlink_event(journal_path, mapping)
        mappings.append(mapping)
        recorded_targets.add(final_target)
        changed = True

    # Single atomic manifest write after the loop (was once-per-item, O(n²)). If a crash strikes
    # mid-loop the manifest may lag the journal; full orphan-symlink reconciliation is owned by
    # Story 3.5 (rollback) / 3.6 (idempotency), which replay the authoritative journal.
    if changed:
        _write_manifest(root, mappings)

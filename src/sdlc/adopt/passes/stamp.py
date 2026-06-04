"""Pass 3 — stamp adopted artifacts as imported-from-existing (Story 3.4).

Reads the frozen ``adopted-symlinks.json`` manifest (Pass 2 output), appends one
``imported_from_existing`` journal event per accepted mapping, and writes EXTERNAL metadata
at ``.claude/state/imported-metadata/<artifact-id>.yaml``. Source artifacts are never
modified (NFR-REL-6).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from sdlc.adopt.imported_metadata import (
    ImportedMetadataRecord,
    metadata_record_path,
    read_metadata_record,
    record_to_yaml_bytes,
)
from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes._frontmatter import read_lenient_frontmatter
from sdlc.adopt.passes._symlink import is_target_under_root
from sdlc.adopt.passes.symlink_offer import _load_existing_mappings
from sdlc.concurrency.io_primitives import atomic_write_bytes
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.ids.clock import now_rfc3339_utc_ms
from sdlc.journal import allocate_next_seq_for_append_sync, append_sync

_KIND_IMPORTED: Final[str] = "imported_from_existing"
_MARKER: Final[str] = "imported-from-existing"
_ACTOR: Final[str] = "cli"
_TARGET_ID: Final[str] = "adopt"
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64

WarnCallback = Callable[[str], None]


def _append_imported_event(journal_path: Path, mapping: SymlinkMapping, *, ts: str) -> None:
    """Append an event-only ``imported_from_existing`` entry (D4(a)).

    ``ts`` is sampled once by the caller and reused for BOTH this journal event and the
    sidecar's ``imported_at`` (mirrors Pass 2's single-timestamp invariant in
    ``_accept._append_symlink_event``) so the two records cross-reference by time.
    """
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=_ACTOR,
        kind=_KIND_IMPORTED,
        target_id=_TARGET_ID,
        before_hash=None,
        after_hash=_ZERO_HASH,
        payload={
            "source": mapping.source,
            "target": mapping.target,
            "marker": _MARKER,
        },
    )
    append_sync(entry, journal_path=journal_path)


def _write_metadata_record(
    root: Path, mapping: SymlinkMapping, *, imported_at: str, warn: WarnCallback | None
) -> None:
    """Write one EXTERNAL metadata sidecar (AC2); fail-soft on OSError."""
    frontmatter: dict[str, object] | None = None
    target_path = root / mapping.target
    if mapping.target.endswith(".md"):
        frontmatter = read_lenient_frontmatter(target_path)

    record = ImportedMetadataRecord(
        source=mapping.source,
        target=mapping.target,
        kind=mapping.kind,
        imported_at=imported_at,
        frontmatter=frontmatter,
    )
    record_path = metadata_record_path(root, mapping.target).resolve()
    assert_path_under_claude(root, record_path)
    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(record_path, record_to_yaml_bytes(record))
    except OSError as exc:
        if warn is not None:
            warn(
                f"could not write imported-metadata for {mapping.target!r}: {exc}; "
                "journal entry was still recorded"
            )


def _mapping_stampable(root: Path, mapping: SymlinkMapping, *, warn: WarnCallback | None) -> bool:
    if not (
        is_target_under_root(root, mapping.target) and is_target_under_root(root, mapping.source)
    ):
        if warn is not None:
            warn(f"skipping stamp for {mapping.target!r}: target/source escapes the project root")
        return False
    record_path = metadata_record_path(root, mapping.target)
    if read_metadata_record(record_path) is not None:
        return False  # already stamped → idempotent re-run no-op (D6 / CR3.4-W8)
    if record_path.exists():
        # Sidecar present but unreadable/corrupt: do NOT re-journal every run (that would break
        # idempotency). Warn rather than silently swallow (CR3.3-P3) and leave it for repair.
        if warn is not None:
            warn(
                f"imported-metadata sidecar for {mapping.target!r} is present but unreadable; "
                "skipping re-stamp"
            )
        return False
    return True


def mark_imported(
    root: Path,
    detected: Sequence[DetectedArtifact],
    *,
    journal_path: Path | None = None,
    warn: WarnCallback | None = None,
) -> None:
    """Stamp every accepted symlink from the manifest (Story 3.4; 3.1 was a no-op).

    The stamp loop is manifest-driven (A), not ``detected``-driven — ``detected`` is kept
    for 3.1 orchestrator-ordering stability (D6). ``journal_path=None`` ⇒ no journaling
    (resume / ordering-test no-op default, mirroring Pass 2).
    """
    _ = detected  # seam stability only; authoritative input is the manifest
    mappings = _load_existing_mappings(root, warn=warn)
    if not mappings:
        return

    # Dedup duplicate manifest targets within one run (a forged/merged-resume manifest can carry
    # them; Pass 2's `recorded_targets` only collapses dupes it creates) so one target stamps once.
    seen_targets: set[str] = set()
    for mapping in mappings:
        if mapping.target in seen_targets:
            continue
        seen_targets.add(mapping.target)
        # Validate BOTH paths stay under the project root BEFORE any side effect (journal or
        # sidecar). `mapping.target`/`source` come from the on-disk manifest (untrusted JSON);
        # an unguarded `root / mapping.target` would let a `..`-bearing target read an arbitrary
        # file (whose bytes flow into the sidecar + the verifier prompt). Skip-and-warn keeps the
        # pass fail-soft instead of stamping an escaping path.
        if not _mapping_stampable(root, mapping, warn=warn):
            continue
        imported_at = now_rfc3339_utc_ms()
        try:
            if journal_path is not None:
                _append_imported_event(journal_path, mapping, ts=imported_at)
            _write_metadata_record(root, mapping, imported_at=imported_at, warn=warn)
        except OSError as exc:
            if warn is not None:
                warn(f"skipping stamp for {mapping.target!r}: {exc}")
            continue

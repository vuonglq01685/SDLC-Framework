"""Mutation-kill tests for stamp.py + rollback.py + imported_metadata.py (Story 3.7 AC2).

Targets the 22+26+38 surviving mutants by exercising:
- stamp.py: idempotency (already-stamped skips), both source+target under root guard,
  duplicate target in manifest stamped once, corrupt sidecar warns, journal fields
- rollback.py: single vs multi-target journal payload, targets=None removes all,
  len(to_remove)==1 → individual payload, len>1 → summary payload
- imported_metadata.py: artifact_id_for_target char replacements, truncation at 200,
  read_metadata_record None for missing, warns+None for corrupt, record_to_yaml_bytes format
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

import yaml

from sdlc.adopt.imported_metadata import (
    ImportedMetadataRecord,
    artifact_id_for_target,
    metadata_record_path,
    read_metadata_record,
    record_to_yaml_bytes,
)
from sdlc.adopt.passes.stamp import mark_imported
from sdlc.adopt.rollback import rollback
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_MANIFEST_REL = ".claude/state/adopted-symlinks.json"
_JOURNAL_REL = ".claude/state/journal.log"
_ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"
_TS_ACCEPTED = "2026-06-04T12:00:00.000Z"
_ZERO = "sha256:" + "0" * 64


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "journal.log").touch()
    return tmp_path


def _mapping(
    source: str = "docs/arch.md",
    target: str = _ARCH_TARGET,
    kind: str = "architecture",
) -> SymlinkMapping:
    return SymlinkMapping(source=source, target=target, accepted_at=_TS_ACCEPTED, kind=kind)  # type: ignore[arg-type]


def _write_manifest(root: Path, mappings: list[SymlinkMapping]) -> None:
    text = json.dumps(
        AdoptedSymlinks(mappings=tuple(mappings)).model_dump(mode="json"),
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    path = root / _MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((unicodedata.normalize("NFC", text) + "\n").encode("utf-8"))


def _write_source(root: Path, rel: str, body: str = "# src\n") -> Path:
    src = root / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body, encoding="utf-8")
    return src


def _link(root: Path, source_rel: str, target_rel: str) -> None:
    src = root / source_rel
    slot = root / target_rel
    slot.parent.mkdir(parents=True, exist_ok=True)
    if slot.is_symlink() or slot.exists():
        slot.unlink()
    os.symlink(os.path.relpath(src.resolve(), slot.parent.resolve()), slot)


def _journal_entries(root: Path) -> list[JournalEntry]:
    text = (root / _JOURNAL_REL).read_text(encoding="utf-8")
    return [JournalEntry.model_validate_json(ln) for ln in text.splitlines() if ln.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ===========================================================================
# stamp.py
# ===========================================================================


# --- Idempotency ---


def test_stamp_already_stamped_is_no_op(tmp_path: Path) -> None:
    """If sidecar already exists and is valid, mark_imported skips without re-journaling."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])
    journal_path = root / _JOURNAL_REL

    # First stamp
    mark_imported(root, [], journal_path=journal_path)
    entries_after_first = _journal_entries(root)
    imported_first = [e for e in entries_after_first if e.kind == "imported_from_existing"]
    assert len(imported_first) == 1

    # Second stamp — must NOT produce another journal entry
    mark_imported(root, [], journal_path=journal_path)
    entries_after_second = _journal_entries(root)
    imported_second = [e for e in entries_after_second if e.kind == "imported_from_existing"]
    assert len(imported_second) == 1  # still exactly 1, not 2


def test_stamp_sidecar_written(tmp_path: Path) -> None:
    """mark_imported writes a sidecar YAML file at the expected path."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    sidecar = metadata_record_path(root, _ARCH_TARGET)
    assert sidecar.exists()


def test_stamp_journal_entry_payload_fields(tmp_path: Path) -> None:
    """imported_from_existing journal entry carries source, target, and marker."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping(source="docs/arch.md", target=_ARCH_TARGET)])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    entries = _journal_entries(root)
    imported = [e for e in entries if e.kind == "imported_from_existing"]
    assert len(imported) == 1
    payload = imported[0].payload
    assert payload["source"] == "docs/arch.md"
    assert payload["target"] == _ARCH_TARGET
    assert payload["marker"] == "imported-from-existing"


def test_stamp_journal_entry_after_hash_is_zero_sentinel(tmp_path: Path) -> None:
    """imported_from_existing entry uses event-only zero hash."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    for e in _journal_entries(root):
        assert e.after_hash == _ZERO
        assert e.before_hash is None


def test_stamp_duplicate_target_in_manifest_stamped_once(tmp_path: Path) -> None:
    """Duplicate target entries in manifest are stamped at most once."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    # Two mappings with the same target (possible from a forged/merged manifest)
    dup_mapping = _mapping(source="docs/arch.md", target=_ARCH_TARGET)
    _write_manifest(root, [dup_mapping, dup_mapping])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    entries = _journal_entries(root)
    imported = [e for e in entries if e.kind == "imported_from_existing"]
    assert len(imported) == 1  # not 2


def test_stamp_skips_escaping_target(tmp_path: Path) -> None:
    """mark_imported skips mappings where target escapes the project root."""
    root = _scaffold(tmp_path)
    # Tampered manifest: target escapes root
    escaping = _mapping(source="docs/arch.md", target="../escape.md")
    _write_manifest(root, [escaping])
    warns: list[str] = []

    mark_imported(root, [], journal_path=root / _JOURNAL_REL, warn=warns.append)

    # No sidecar created for escaping target
    sidecar = metadata_record_path(root, "../escape.md")
    assert not sidecar.exists()
    assert any("escapes" in w for w in warns)


def test_stamp_corrupt_sidecar_warns_and_does_not_restamp(tmp_path: Path) -> None:
    """If sidecar exists but is corrupt, warn (not silently skip) and don't re-stamp."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])
    sidecar = metadata_record_path(root, _ARCH_TARGET)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("marker: imported-from-existing\n[BAD YAML\n", encoding="utf-8")
    warns: list[str] = []

    mark_imported(root, [], journal_path=root / _JOURNAL_REL, warn=warns.append)

    # No new journal entry (idempotency of corrupt sidecar)
    imported = [e for e in _journal_entries(root) if e.kind == "imported_from_existing"]
    assert len(imported) == 0
    assert any("unreadable" in w or "corrupt" in w or "skipping" in w for w in warns)


def test_stamp_source_must_also_be_under_root(tmp_path: Path) -> None:
    """mark_imported skips when source escapes the project root."""
    root = _scaffold(tmp_path)
    escaping = _mapping(source="../outside.md", target=_ARCH_TARGET)
    _write_manifest(root, [escaping])
    warns: list[str] = []

    mark_imported(root, [], journal_path=root / _JOURNAL_REL, warn=warns.append)

    # No sidecar or journal entry (source escaping root is rejected)
    imported = [e for e in _journal_entries(root) if e.kind == "imported_from_existing"]
    assert len(imported) == 0
    assert any("escapes" in w for w in warns)


def test_stamp_empty_manifest_is_no_op(tmp_path: Path) -> None:
    """mark_imported with empty manifest does nothing (no crash, no entries)."""
    root = _scaffold(tmp_path)
    _write_manifest(root, [])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    entries = _journal_entries(root)
    assert len(entries) == 0


# ===========================================================================
# rollback.py
# ===========================================================================


def test_rollback_single_target_has_individual_journal_payload(tmp_path: Path) -> None:
    """Single-target rollback uses individual payload {target, source}, not summary."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping(source="docs/arch.md", target=_ARCH_TARGET)])
    _link(root, "docs/arch.md", _ARCH_TARGET)
    journal_path = root / _JOURNAL_REL

    rollback(root, targets=[_ARCH_TARGET], journal_path=journal_path)

    rolled = [e for e in _journal_entries(root) if e.kind == "symlink_rolled_back"]
    assert len(rolled) == 1
    # Individual payload: has "target" and "source" keys, NOT "count"
    assert "target" in rolled[0].payload
    assert "source" in rolled[0].payload
    assert "count" not in rolled[0].payload


def test_rollback_two_targets_has_summary_journal_payload(tmp_path: Path) -> None:
    """Two-target rollback uses summary payload {count, targets}, not individual."""
    root = _scaffold(tmp_path)
    t1 = _ARCH_TARGET
    t2 = "01-Requirement/01-PRODUCT.md"
    _write_source(root, "docs/arch.md")
    _write_source(root, "docs/prd.md")
    _write_manifest(root, [
        _mapping(source="docs/arch.md", target=t1),
        _mapping(source="docs/prd.md", target=t2, kind="prd"),
    ])
    _link(root, "docs/arch.md", t1)
    _link(root, "docs/prd.md", t2)
    journal_path = root / _JOURNAL_REL

    rollback(root, targets=[t1, t2], journal_path=journal_path)

    rolled = [e for e in _journal_entries(root) if e.kind == "symlink_rolled_back"]
    assert len(rolled) == 1
    # Summary payload
    assert rolled[0].payload["count"] == 2
    assert set(rolled[0].payload["targets"]) == {t1, t2}
    assert "source" not in rolled[0].payload


def test_rollback_targets_none_uses_summary_payload(tmp_path: Path) -> None:
    """targets=None rollback uses summary payload (len(to_remove) > 1 for 2 items)."""
    root = _scaffold(tmp_path)
    t1 = _ARCH_TARGET
    t2 = "01-Requirement/01-PRODUCT.md"
    _write_source(root, "docs/arch.md")
    _write_source(root, "docs/prd.md")
    _write_manifest(root, [
        _mapping(source="docs/arch.md", target=t1),
        _mapping(source="docs/prd.md", target=t2, kind="prd"),
    ])
    _link(root, "docs/arch.md", t1)
    _link(root, "docs/prd.md", t2)
    journal_path = root / _JOURNAL_REL

    result = rollback(root, targets=None, journal_path=journal_path)

    assert set(result.removed_targets) == {t1, t2}
    rolled = [e for e in _journal_entries(root) if e.kind == "symlink_rolled_back"]
    assert len(rolled) == 1
    assert rolled[0].payload["count"] == 2


def test_rollback_single_target_removes_from_manifest(tmp_path: Path) -> None:
    """Rolling back a single target removes exactly that entry from the manifest."""
    root = _scaffold(tmp_path)
    t1 = _ARCH_TARGET
    t2 = "01-Requirement/01-PRODUCT.md"
    _write_source(root, "docs/arch.md")
    _write_source(root, "docs/prd.md")
    _write_manifest(root, [
        _mapping(source="docs/arch.md", target=t1),
        _mapping(source="docs/prd.md", target=t2, kind="prd"),
    ])
    _link(root, "docs/arch.md", t1)
    journal_path = root / _JOURNAL_REL

    rollback(root, targets=[t1], journal_path=journal_path)

    manifest = AdoptedSymlinks.model_validate_json(
        (root / _MANIFEST_REL).read_text(encoding="utf-8")
    )
    remaining_targets = {m.target for m in manifest.mappings}
    assert t1 not in remaining_targets
    assert t2 in remaining_targets  # must NOT be removed


def test_rollback_other_pointing_symlink_warns_leaves_untouched(tmp_path: Path) -> None:
    """Symlink pointing to different source → warn and leave it, still prune manifest."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_source(root, "docs/other.md")
    _write_manifest(root, [_mapping(source="docs/arch.md", target=_ARCH_TARGET)])
    # Put a symlink that points to a DIFFERENT source
    _link(root, "docs/other.md", _ARCH_TARGET)
    warns: list[str] = []
    journal_path = root / _JOURNAL_REL

    result = rollback(root, targets=[_ARCH_TARGET], journal_path=journal_path, warn=warns.append)

    # Symlink NOT removed (it's pointing elsewhere)
    assert (root / _ARCH_TARGET).is_symlink()
    assert any("no longer points" in w or "different" in w or "untouched" in w for w in warns)
    # Manifest entry still pruned
    manifest = AdoptedSymlinks.model_validate_json(
        (root / _MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert all(m.target != _ARCH_TARGET for m in manifest.mappings)
    assert result.removed_targets == (_ARCH_TARGET,)


def test_rollback_journal_entry_schema_version_one(tmp_path: Path) -> None:
    """symlink_rolled_back entry has schema_version=1."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])
    _link(root, "docs/arch.md", _ARCH_TARGET)

    rollback(root, targets=[_ARCH_TARGET], journal_path=root / _JOURNAL_REL)

    for e in _journal_entries(root):
        assert e.schema_version == 1


def test_rollback_missing_target_raises_before_any_removal(tmp_path: Path) -> None:
    """targets=[unknown] raises AdoptError before any symlink is touched."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/arch.md")
    _write_manifest(root, [_mapping()])
    _link(root, "docs/arch.md", _ARCH_TARGET)

    with pytest.raises(AdoptError, match="not in adopted-symlinks manifest"):
        rollback(root, targets=["nonexistent/target.md"], journal_path=root / _JOURNAL_REL)

    # The existing symlink must still be intact
    assert (root / _ARCH_TARGET).is_symlink()


# ===========================================================================
# imported_metadata.py
# ===========================================================================


@pytest.mark.parametrize("target, expected_id", [
    ("docs/arch.md", "docs__arch.md"),
    ("02-Architecture/02-System/ARCHITECTURE.md", "02-Architecture__02-System__ARCHITECTURE.md"),
    ("path with spaces.md", "path with spaces.md"),  # spaces not replaced (only /)
    ("path:with:colons.md", "path_with_colons.md"),
    ("path<angle>.md", "path_angle_.md"),
])
def test_artifact_id_for_target_slash_replaced(target: str, expected_id: str) -> None:
    """artifact_id_for_target replaces '/' with '__' (and other unsafe chars with '_')."""
    result = artifact_id_for_target(target)
    assert result == expected_id


def test_artifact_id_for_target_truncates_at_200(  ) -> None:
    """artifact_id_for_target truncates at exactly 200 characters."""
    long_target = "a" * 250
    result = artifact_id_for_target(long_target)
    assert len(result) == 200


def test_artifact_id_for_target_under_200_not_truncated(  ) -> None:
    """Short targets under 200 chars are returned unchanged (modulo char mapping)."""
    target = "docs/short.md"
    result = artifact_id_for_target(target)
    assert len(result) < 200
    assert result == "docs__short.md"


def test_artifact_id_for_target_exactly_200_not_truncated(  ) -> None:
    """Target of exactly 200 chars (after mapping) is NOT truncated."""
    target = "a" * 200
    result = artifact_id_for_target(target)
    assert len(result) == 200


def test_read_metadata_record_returns_none_for_missing(tmp_path: Path) -> None:
    """read_metadata_record returns None when the file doesn't exist."""
    path = tmp_path / "nonexistent.yaml"
    result = read_metadata_record(path)
    assert result is None


def test_read_metadata_record_returns_record_for_valid_file(tmp_path: Path) -> None:
    """read_metadata_record returns an ImportedMetadataRecord for a valid YAML file."""
    record = ImportedMetadataRecord(
        source="docs/arch.md",
        target=_ARCH_TARGET,
        kind="architecture",
        imported_at="2026-06-04T12:00:00.000Z",
    )
    path = tmp_path / "record.yaml"
    path.write_bytes(record_to_yaml_bytes(record))

    result = read_metadata_record(path)
    assert result is not None
    assert result.source == "docs/arch.md"
    assert result.target == _ARCH_TARGET
    assert result.kind == "architecture"
    assert result.marker == "imported-from-existing"


def test_read_metadata_record_returns_none_for_corrupt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """read_metadata_record returns None (not raises) for a corrupt YAML file."""
    path = tmp_path / "corrupt.yaml"
    path.write_text("{ invalid: yaml: content: [\n", encoding="utf-8")

    result = read_metadata_record(path)
    assert result is None


def test_read_metadata_record_logs_warning_for_corrupt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """read_metadata_record logs a warning (not silently swallows) for corrupt sidecar."""
    import logging

    path = tmp_path / "corrupt.yaml"
    path.write_text("not_yaml: [bad\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="sdlc.adopt.imported_metadata"):
        read_metadata_record(path)

    assert any("unreadable" in r.message or "corrupt" in r.message for r in caplog.records)


def test_record_to_yaml_bytes_is_valid_yaml(  ) -> None:
    """record_to_yaml_bytes produces valid YAML that round-trips through yaml.safe_load."""
    record = ImportedMetadataRecord(
        source="docs/arch.md",
        target=_ARCH_TARGET,
        kind="architecture",
        imported_at="2026-06-04T12:00:00.000Z",
    )
    raw = record_to_yaml_bytes(record)
    parsed = yaml.safe_load(raw.decode("utf-8"))
    assert parsed["marker"] == "imported-from-existing"
    assert parsed["source"] == "docs/arch.md"


def test_record_to_yaml_bytes_ends_with_newline(  ) -> None:
    """record_to_yaml_bytes output ends with a newline (canonical format)."""
    record = ImportedMetadataRecord(
        source="docs/arch.md",
        target=_ARCH_TARGET,
        kind="architecture",
        imported_at="2026-06-04T12:00:00.000Z",
    )
    raw = record_to_yaml_bytes(record)
    assert raw.endswith(b"\n")


def test_record_to_yaml_bytes_is_nfc_normalized(  ) -> None:
    """record_to_yaml_bytes text is NFC-normalized UTF-8."""
    record = ImportedMetadataRecord(
        source="docs/arch.md",
        target=_ARCH_TARGET,
        kind="architecture",
        imported_at="2026-06-04T12:00:00.000Z",
    )
    raw = record_to_yaml_bytes(record)
    text = raw.decode("utf-8")
    assert text == unicodedata.normalize("NFC", text)


def test_metadata_record_path_uses_artifact_id(tmp_path: Path) -> None:
    """metadata_record_path constructs path using artifact_id_for_target slug."""
    root = tmp_path
    target = "02-Architecture/02-System/ARCHITECTURE.md"
    expected_id = artifact_id_for_target(target)
    result = metadata_record_path(root, target)
    assert result.name == f"{expected_id}.yaml"


def test_metadata_record_path_under_claude_state(tmp_path: Path) -> None:
    """metadata_record_path returns a path under .claude/state/imported-metadata/."""
    root = tmp_path
    result = metadata_record_path(root, "docs/arch.md")
    relative = result.relative_to(root)
    parts = relative.parts
    assert parts[0] == ".claude"
    assert parts[1] == "state"
    assert parts[2] == "imported-metadata"

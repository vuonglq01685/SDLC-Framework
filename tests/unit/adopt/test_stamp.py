"""Unit tests for Pass 3 — stamp imported-from-existing (Story 3.4)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest
import yaml

if sys.platform == "win32":  # pragma: no cover - adopt mode is POSIX-only (ADR-034)
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.imported_metadata import artifact_id_for_target, metadata_record_path
from sdlc.adopt.passes.stamp import mark_imported
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit

_MANIFEST_REL = ".claude/state/adopted-symlinks.json"
_JOURNAL_REL = ".claude/state/journal.log"
_ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"
_MARKER = "imported-from-existing"
_ZERO = "sha256:" + "0" * 64


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "journal.log").touch()
    return tmp_path


def _manifest_bytes(mappings: list[SymlinkMapping]) -> bytes:
    text = json.dumps(
        AdoptedSymlinks(mappings=tuple(mappings)).model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _write_manifest(root: Path, mappings: list[SymlinkMapping]) -> None:
    (root / _MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / _MANIFEST_REL).write_bytes(_manifest_bytes(mappings))


def _mapping(
    *,
    source: str = "docs/architecture-2024.md",
    target: str = _ARCH_TARGET,
    kind: str = "architecture",
) -> SymlinkMapping:
    return SymlinkMapping(
        source=source,
        target=target,
        accepted_at="2026-06-04T12:00:00.000Z",
        kind=kind,  # type: ignore[arg-type]
    )


def _journal_entries(root: Path) -> list[JournalEntry]:
    text = (root / _JOURNAL_REL).read_text(encoding="utf-8")
    return [JournalEntry.model_validate_json(ln) for ln in text.splitlines() if ln.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_empty_manifest_is_no_op(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    _write_manifest(root, [])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)
    assert _journal_entries(root) == []


def test_two_mappings_produce_two_journal_events(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    m1 = _mapping()
    m2 = _mapping(
        source="legacy/pom.xml",
        target="03-Implementation/pom.xml",
        kind="build-file",
    )
    _write_manifest(root, [m1, m2])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    imported = [e for e in _journal_entries(root) if e.kind == "imported_from_existing"]
    assert len(imported) == 2
    assert imported[0].payload == {
        "source": m1.source,
        "target": m1.target,
        "marker": _MARKER,
    }
    assert imported[0].after_hash == _ZERO
    assert imported[0].before_hash is None
    assert imported[0].actor == "cli"
    assert imported[0].target_id == "adopt"


def test_md_target_writes_metadata_with_frontmatter(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    src = root / "docs/architecture-2024.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\ntitle: Legacy Arch\n---\n# Body\n", encoding="utf-8")
    mapping = _mapping()
    target = root / mapping.target
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(src, target.parent), target)
    _write_manifest(root, [mapping])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    record_path = metadata_record_path(root, mapping.target)
    assert record_path.exists()
    data = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    assert data["source"] == mapping.source
    assert data["target"] == mapping.target
    assert data["marker"] == _MARKER
    assert data["frontmatter"] == {"title": "Legacy Arch"}
    assert record_path.name == f"{artifact_id_for_target(mapping.target)}.yaml"


def test_md_without_frontmatter_records_null(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    src = root / "docs/plain.md"
    src.parent.mkdir(parents=True)
    src.write_text("# No frontmatter\n", encoding="utf-8")
    mapping = _mapping(source="docs/plain.md", target="01-Requirement/01-PRODUCT.md", kind="prd")
    target = root / mapping.target
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(src, target.parent), target)
    _write_manifest(root, [mapping])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    data = yaml.safe_load(metadata_record_path(root, mapping.target).read_text(encoding="utf-8"))
    assert data["frontmatter"] is None


def test_non_md_target_skips_frontmatter_read(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    mapping = _mapping(
        source="legacy/pom.xml",
        target="03-Implementation/pom.xml",
        kind="build-file",
    )
    _write_manifest(root, [mapping])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    data = yaml.safe_load(metadata_record_path(root, mapping.target).read_text(encoding="utf-8"))
    assert data["frontmatter"] is None


def test_source_bytes_unchanged_after_stamp(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    src = root / "docs/architecture-2024.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\ntitle: X\n---\ncontent\n", encoding="utf-8")
    before = _sha256(src)
    _write_manifest(root, [_mapping()])
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)
    assert _sha256(src) == before


def test_missing_manifest_is_no_op(tmp_path: Path) -> None:
    """An absent adopted-symlinks.json (not just an empty one) → no events, no crash."""
    root = _scaffold(tmp_path)
    # deliberately do NOT write a manifest
    mark_imported(root, [], journal_path=root / _JOURNAL_REL)
    assert _journal_entries(root) == []


def test_unsafe_target_is_skipped_with_warning(tmp_path: Path) -> None:
    """Fail-soft: a manifest target/source that escapes the root warns + is skipped; a valid
    mapping in the same manifest is still stamped (one bad entry never aborts the pass)."""
    root = _scaffold(tmp_path)
    warnings: list[str] = []
    bad = _mapping(source="docs/x.md", target="../../escape.md", kind="prd")
    good = _mapping()  # valid 02-Architecture target
    _write_manifest(root, [bad, good])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL, warn=warnings.append)

    assert any("escapes the project root" in w for w in warnings)
    imported = [e for e in _journal_entries(root) if e.kind == "imported_from_existing"]
    assert len(imported) == 1
    assert imported[0].payload["target"] == good.target


def test_metadata_write_failure_warns_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-soft: an OSError writing the sidecar warns (never silent) and the journal event,
    appended first, is still recorded — the pass does not abort."""
    root = _scaffold(tmp_path)
    warnings: list[str] = []

    from sdlc.adopt.passes import stamp as stamp_mod

    def _boom(path: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(stamp_mod, "atomic_write_bytes", _boom)
    _write_manifest(root, [_mapping()])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL, warn=warnings.append)

    assert any("could not write imported-metadata" in w for w in warnings)
    imported = [e for e in _journal_entries(root) if e.kind == "imported_from_existing"]
    assert len(imported) == 1


def test_journal_ts_matches_sidecar_imported_at(tmp_path: Path) -> None:
    """P6: the journal event `ts` and the sidecar `imported_at` are the SAME sampled timestamp."""
    root = _scaffold(tmp_path)
    mapping = _mapping(source="docs/plain.md", target="01-Requirement/01-PRODUCT.md", kind="prd")
    src = root / mapping.source
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# plain\n", encoding="utf-8")
    target = root / mapping.target
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(src, target.parent), target)
    _write_manifest(root, [mapping])

    mark_imported(root, [], journal_path=root / _JOURNAL_REL)

    event = next(e for e in _journal_entries(root) if e.kind == "imported_from_existing")
    data = yaml.safe_load(metadata_record_path(root, mapping.target).read_text(encoding="utf-8"))
    assert event.ts == data["imported_at"]


def test_stamp_imports_no_forbidden_layers() -> None:
    import sdlc.adopt.passes._frontmatter as fm_mod
    import sdlc.adopt.passes.stamp as mod

    forbidden_layers = (
        "sdlc.cli",
        "sdlc.engine",
        "sdlc.dispatcher",
        "sdlc.runtime",
        "sdlc.specialists",
    )
    for module in (mod, fm_mod):
        src = Path(module.__file__).read_text(encoding="utf-8")
        for layer in forbidden_layers:
            assert layer not in src, f"{module.__name__} must not import {layer}"

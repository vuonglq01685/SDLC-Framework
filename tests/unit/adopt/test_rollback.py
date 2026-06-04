"""Unit tests for adopt rollback core (Story 3.5)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.imported_metadata import metadata_record_path
from sdlc.adopt.rollback import rollback
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.errors import AdoptError
from unit.adopt._symlink_offer_common import (
    ARCH_TARGET,
    JOURNAL_REL,
    MANIFEST_REL,
    journal_entries,
    scaffold,
)

pytestmark = pytest.mark.unit

_TS = "2026-06-04T12:00:00.000Z"
_OTHER_TARGETS = (
    "01-Product/01-Vision/PRODUCT.md",
    "03-Engineering/01-Repo/REPO.md",
    "04-Quality/01-Test-Strategy/TEST-STRATEGY.md",
    "05-Operations/01-Runbooks/RUNBOOKS.md",
)


def _manifest_bytes(mappings: list[SymlinkMapping]) -> bytes:
    text = json.dumps(
        AdoptedSymlinks(mappings=tuple(mappings)).model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _write_manifest(root: Path, mappings: list[SymlinkMapping]) -> None:
    path = root / MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_manifest_bytes(mappings))


def _mapping(*, source: str, target: str, kind: str = "architecture") -> SymlinkMapping:
    return SymlinkMapping(source=source, target=target, accepted_at=_TS, kind=kind)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _link_source_to_target(root: Path, source_rel: str, target_rel: str) -> None:
    src = root / source_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        src.write_text(f"# {source_rel}\n", encoding="utf-8")
    slot = root / target_rel
    slot.parent.mkdir(parents=True, exist_ok=True)
    if slot.exists() or slot.is_symlink():
        slot.unlink()
    rel = os.path.relpath(src.resolve(), slot.parent.resolve())
    os.symlink(rel, slot)


def _five_mapping_manifest() -> list[SymlinkMapping]:
    mappings = [_mapping(source="docs/arch.md", target=ARCH_TARGET)]
    for i, tgt in enumerate(_OTHER_TARGETS):
        mappings.append(_mapping(source=f"docs/other-{i}.md", target=tgt, kind="readme"))
    return mappings


def test_single_target_removes_one_symlink_prunes_manifest_journals(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    mappings = _five_mapping_manifest()
    _write_manifest(root, mappings)
    for m in mappings:
        _link_source_to_target(root, m.source, m.target)

    arch_src = root / "docs/arch.md"
    before = _sha256_file(arch_src)
    journal_path = root / JOURNAL_REL

    result = rollback(root, targets=[ARCH_TARGET], journal_path=journal_path)
    assert result.removed_targets == (ARCH_TARGET,)
    assert not (root / ARCH_TARGET).exists()
    assert _sha256_file(arch_src) == before

    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert len(manifest.mappings) == 4
    assert all(m.target != ARCH_TARGET for m in manifest.mappings)

    rolled = [e for e in journal_entries(root) if e.kind == "symlink_rolled_back"]
    assert len(rolled) == 1
    assert rolled[0].payload == {"target": ARCH_TARGET, "source": "docs/arch.md"}


def test_target_not_in_manifest_raises_adopt_error(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    _write_manifest(root, [_mapping(source="docs/a.md", target=ARCH_TARGET)])
    journal_path = root / JOURNAL_REL
    with pytest.raises(AdoptError, match="not in adopted-symlinks manifest"):
        rollback(root, targets=["missing/path.md"], journal_path=journal_path)
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert len(manifest.mappings) == 1


def test_rollback_all_empties_manifest_one_summary_journal(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    mappings = [
        _mapping(source="docs/a.md", target="01-Product/01-Vision/PRODUCT.md", kind="readme"),
        _mapping(source="docs/b.md", target="03-Engineering/01-Repo/REPO.md", kind="readme"),
        _mapping(
            source="docs/c.md", target="04-Quality/01-Test-Strategy/TEST-STRATEGY.md", kind="readme"
        ),
    ]
    _write_manifest(root, mappings)
    hashes = []
    for m in mappings:
        _link_source_to_target(root, m.source, m.target)
        hashes.append(_sha256_file(root / m.source))

    journal_path = root / JOURNAL_REL
    result = rollback(root, targets=None, journal_path=journal_path)
    assert set(result.removed_targets) == {m.target for m in mappings}
    for m in mappings:
        assert not (root / m.target).exists()

    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()
    assert (root / MANIFEST_REL).exists()

    rolled = [e for e in journal_entries(root) if e.kind == "symlink_rolled_back"]
    assert len(rolled) == 1
    assert rolled[0].payload["count"] == 3
    assert set(rolled[0].payload["targets"]) == {m.target for m in mappings}

    for m, h in zip(mappings, hashes, strict=True):
        assert _sha256_file(root / m.source) == h


def test_idempotent_slot_already_removed_warns_and_prunes_manifest(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    _write_manifest(root, [_mapping(source="docs/a.md", target=ARCH_TARGET)])
    journal_path = root / JOURNAL_REL
    warns: list[str] = []

    def _warn(msg: str) -> None:
        warns.append(msg)

    result = rollback(root, targets=[ARCH_TARGET], journal_path=journal_path, warn=_warn)
    assert result.removed_targets == (ARCH_TARGET,)
    assert any("already removed" in w for w in warns)
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()


def test_idempotent_real_file_at_slot_warns_leaves_file_prunes_manifest(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    _write_manifest(root, [_mapping(source="docs/a.md", target=ARCH_TARGET)])
    slot = root / ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("user replaced symlink with a real file\n", encoding="utf-8")
    before = slot.read_bytes()
    journal_path = root / JOURNAL_REL
    warns: list[str] = []

    def _warn(msg: str) -> None:
        warns.append(msg)

    result = rollback(root, targets=[ARCH_TARGET], journal_path=journal_path, warn=_warn)
    assert result.removed_targets == (ARCH_TARGET,)
    assert slot.read_bytes() == before
    assert any("no longer an adopt symlink" in w for w in warns)
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()


def test_idempotent_dangling_symlink_unlinked_and_pruned(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    _write_manifest(root, [_mapping(source="docs/a.md", target=ARCH_TARGET)])
    slot = root / ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("nonexistent-source.md", slot)
    journal_path = root / JOURNAL_REL

    result = rollback(root, targets=[ARCH_TARGET], journal_path=journal_path)
    assert result.removed_targets == (ARCH_TARGET,)
    assert not slot.exists()
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()


def test_rollback_prunes_imported_metadata_sidecar(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    _write_manifest(root, [_mapping(source="docs/a.md", target=ARCH_TARGET)])
    _link_source_to_target(root, "docs/a.md", ARCH_TARGET)
    sidecar = metadata_record_path(root, ARCH_TARGET)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("marker: imported-from-existing\n", encoding="utf-8")
    journal_path = root / JOURNAL_REL

    rollback(root, targets=[ARCH_TARGET], journal_path=journal_path)
    assert not sidecar.exists()


def test_rollback_skips_target_escaping_root_leaves_outside_file(tmp_path: Path) -> None:
    # Defense-in-depth (AC5 / NFR-REL-6): SymlinkMapping.target is an unvalidated str, so a
    # tampered manifest could carry a ``..``-escaping target. The core must NOT unlink outside
    # root — it warns + leaves the on-disk path untouched but still prunes the stale entry.
    root = scaffold(tmp_path / "repo")  # nest so the escaping path stays in the test sandbox
    victim = tmp_path / "victim.txt"  # root/../victim.txt — outside root, inside tmp_path
    victim.write_text("must survive\n", encoding="utf-8")
    before = victim.read_bytes()

    escaping_target = "../victim.txt"
    _write_manifest(root, [_mapping(source="docs/a.md", target=escaping_target)])
    journal_path = root / JOURNAL_REL
    warns: list[str] = []

    result = rollback(root, targets=[escaping_target], journal_path=journal_path, warn=warns.append)

    assert victim.read_bytes() == before  # nothing outside root was touched
    assert any("escapes the project root" in w for w in warns)
    assert result.removed_targets == (escaping_target,)
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()  # stale entry still pruned (converge to disk truth)


def test_rollback_core_imports_no_forbidden_layers() -> None:
    import sdlc.adopt.rollback as mod

    forbidden_layers = (
        "sdlc.cli",
        "sdlc.engine",
        "sdlc.dispatcher",
        "sdlc.runtime",
        "sdlc.specialists",
    )
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for layer in forbidden_layers:
        assert layer not in src, f"rollback must not import {layer}"

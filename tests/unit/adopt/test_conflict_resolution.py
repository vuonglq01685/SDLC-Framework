"""Story 3.6 — Pass 2 conflict resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes import _accept, _symlink, symlink_offer
from sdlc.adopt.passes._symlink import SymlinkOutcome
from sdlc.adopt.passes.symlink_offer import (
    ConflictContext,
    ConflictDecision,
    ConflictKind,
)
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.errors import AdoptError
from unit.adopt._symlink_offer_common import (
    ARCH_TARGET,
    accept_all,
    artifact,
    file_sha256,
    journal_entries,
    read_manifest,
    scaffold,
    write_source,
)

pytestmark = pytest.mark.unit

_SOURCE_REL = "docs/architecture-2024.md"
_REAL_FILE_BYTES = "existing real file\n"


def _conflict_dirs(root: Path) -> list[Path]:
    base = root / ".claude/state/adopt-conflicts"
    return sorted(base.glob("*/*.bak")) if base.exists() else []


def test_real_file_conflict_backup_replace(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_REAL_FILE_BYTES, encoding="utf-8")
    journal = root / ".claude/state/journal.log"

    def _backup(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        assert ctx.kind is ConflictKind.REAL_FILE
        return ConflictDecision(action="backup_replace")

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=_backup,
    )

    assert target.is_symlink()
    manifest = read_manifest(root)
    assert len(manifest.mappings) == 1
    # AC2 `b`: the displaced real file's bytes are byte-preserved in the `.bak`.
    backups = _conflict_dirs(root)
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == _REAL_FILE_BYTES
    # AC5 / NFR-REL-6: the adopted SOURCE tree is byte-identical pre/post.
    assert file_sha256(src) == src_digest


def test_real_file_conflict_different_target(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_REAL_FILE_BYTES, encoding="utf-8")
    alt = "02-Architecture/02-System/ARCHITECTURE-ALT.md"
    journal = root / ".claude/state/journal.log"

    def _different(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        assert ctx.kind is ConflictKind.REAL_FILE
        return ConflictDecision(action="different_target", target=alt)

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=_different,
    )

    # The symlink lands at the NEW slot; the original real file is untouched.
    assert (root / alt).is_symlink()
    assert target.is_file() and not target.is_symlink()
    assert target.read_text(encoding="utf-8") == _REAL_FILE_BYTES
    manifest = read_manifest(root)
    assert [m.target for m in manifest.mappings] == [alt]
    assert file_sha256(src) == src_digest


def test_backup_replace_create_failure_restores_real_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_REAL_FILE_BYTES, encoding="utf-8")
    journal = root / ".claude/state/journal.log"
    warnings: list[str] = []

    real_create = _symlink.create_relative_symlink

    def _flaky_create(r: Path, source_rel: str, target_rel: str) -> SymlinkOutcome:
        # Fail ONLY the post-backup create (the slot is empty by then); the initial
        # conflict-detection call still classifies the real file via the real impl.
        slot = r / target_rel
        if not slot.exists() and not slot.is_symlink():
            raise AdoptError("simulated create failure", details={"target": target_rel})
        return real_create(r, source_rel, target_rel)

    monkeypatch.setattr(_accept, "create_relative_symlink", _flaky_create)

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warnings.append,
    )

    # P1: create failed AFTER the backup → the user's real file is RESTORED, not stranded.
    assert target.is_file() and not target.is_symlink()
    assert target.read_text(encoding="utf-8") == _REAL_FILE_BYTES
    assert not (root / ".claude/state/adopted-symlinks.json").exists()  # nothing recorded
    assert any("restored" in w for w in warnings)
    assert file_sha256(src) == src_digest


def test_different_target_unsafe_is_bounded(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_REAL_FILE_BYTES, encoding="utf-8")
    journal = root / ".claude/state/journal.log"
    warnings: list[str] = []

    def _always_unsafe(_a: DetectedArtifact, _t: str, _c: ConflictContext) -> ConflictDecision:
        return ConflictDecision(action="different_target", target="../escape.md")

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=_always_unsafe,
        warn=warnings.append,
    )

    # P9: an unsafe `d` answer re-prompts (bounded) then skips — no infinite loop, no symlink.
    assert not target.is_symlink()
    assert target.is_file()  # the real file is left untouched
    assert not (root / ".claude/state/adopted-symlinks.json").exists()
    assert any("escapes project root" in w for w in warnings)
    assert any("too many different-target attempts" in w for w in warnings)
    assert file_sha256(src) == src_digest


def test_other_symlink_replace_journals_both(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    other_src = write_source(root, "legacy/other.md", body="# Other\n")
    other_digest = file_sha256(other_src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/other.md", target)
    journal = root / ".claude/state/journal.log"

    def _replace(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        assert ctx.kind is ConflictKind.OTHER_SYMLINK
        assert ctx.other_source == "legacy/other.md"
        return ConflictDecision(action="replace")

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=_replace,
    )

    entries = journal_entries(root)
    kinds = [e.kind for e in entries]
    assert "symlink_replaced" in kinds
    assert kinds.count("symlink_accepted") == 1
    # P10: the paired replaced + accepted events share ONE timestamp (single-ts cross-ref).
    replaced = next(e for e in entries if e.kind == "symlink_replaced")
    accepted = next(e for e in entries if e.kind == "symlink_accepted")
    assert replaced.ts == accepted.ts
    assert replaced.payload == {"target": ARCH_TARGET, "old_source": "legacy/other.md"}
    # The manifest records exactly one mapping for the slot (no duplicate-target row).
    assert [m.target for m in read_manifest(root).mappings] == [ARCH_TARGET]
    # Both source trees are byte-identical.
    assert file_sha256(src) == src_digest
    assert file_sha256(other_src) == other_digest


def test_noninteractive_conflict_skips_without_backup(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, _SOURCE_REL)
    src_digest = file_sha256(src)
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("blocker\n", encoding="utf-8")
    journal = root / ".claude/state/journal.log"
    warnings: list[str] = []

    symlink_offer.offer_symlinks(
        root,
        [artifact()],
        confirm=None,
        auto_accept_threshold=80,
        journal_path=journal,
        conflict=None,
        warn=warnings.append,
    )

    assert not target.is_symlink()
    assert target.read_text(encoding="utf-8") == "blocker\n"  # no destructive backup w/o consent
    assert not _conflict_dirs(root)
    assert any("real file" in w for w in warnings)
    assert file_sha256(src) == src_digest

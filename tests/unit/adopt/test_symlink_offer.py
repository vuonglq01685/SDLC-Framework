"""Unit tests for Pass 2 interactive symlink offer (Story 3.3, AC1-AC3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdlc.adopt.passes.symlink_offer import SymlinkDecision, offer_symlinks
from sdlc.contracts.adopt_report import DetectedArtifact
from unit.adopt._symlink_offer_common import (
    ARCH_TARGET,
    JOURNAL_REL,
    MANIFEST_REL,
    accept_all,
    artifact,
    journal_entries,
    read_manifest,
    reject_all,
    scaffold,
    write_source,
)

pytestmark = pytest.mark.unit

# --- AC1 / AC2: interactive accept creates a relative symlink + records + journals -----------


def test_interactive_accept_creates_relative_symlink(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, "docs/architecture-2024.md")
    offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    target = root / ARCH_TARGET
    assert target.is_symlink()
    link = os.readlink(target)
    assert not os.path.isabs(link), f"symlink must be relative, got {link!r}"
    assert (target.parent / link).resolve() == src.resolve()


def test_interactive_accept_records_mapping_in_manifest(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(root, [artifact()], confirm=accept_all, auto_accept_threshold=80)
    manifest = read_manifest(root)
    assert len(manifest.mappings) == 1
    m = manifest.mappings[0]
    assert m.source == "docs/architecture-2024.md"
    assert m.target == ARCH_TARGET
    assert m.kind == "architecture"
    assert m.accepted_at.endswith("Z")


def test_interactive_accept_emits_symlink_accepted_journal_entry(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    entries = journal_entries(root)
    accepted = [e for e in entries if e.kind == "symlink_accepted"]
    assert len(accepted) == 1
    payload = accepted[0].payload
    assert payload["source"] == "docs/architecture-2024.md"
    assert payload["target"] == ARCH_TARGET
    assert payload["kind"] == "architecture"


def test_confirm_receives_integer_confidence(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    seen: list[int] = []

    def confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        seen.append(art.confidence)
        return SymlinkDecision(accept=True, target=target)

    offer_symlinks(root, [artifact(confidence=85)], confirm=confirm, auto_accept_threshold=80)
    assert seen == [85]
    assert isinstance(seen[0], int)


# --- AC1: skip + edit ------------------------------------------------------------------------


def test_interactive_reject_creates_nothing(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(
        root,
        [artifact()],
        confirm=reject_all,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    assert not (root / ARCH_TARGET).exists()
    assert not (root / MANIFEST_REL).exists()
    assert [e for e in journal_entries(root) if e.kind == "symlink_accepted"] == []


def test_edit_overrides_target(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, "docs/architecture-2024.md")
    edited = "02-Architecture/02-System/SYSTEM.md"

    def confirm(_art: DetectedArtifact, _target: str) -> SymlinkDecision:
        return SymlinkDecision(accept=True, target=edited)  # D3: user edited the target

    offer_symlinks(root, [artifact()], confirm=confirm, auto_accept_threshold=80)
    assert (root / edited).is_symlink()
    assert (root / edited).resolve() == src.resolve()
    assert read_manifest(root).mappings[0].target == edited


# --- AC1 / AC3: threshold gating -------------------------------------------------------------


def test_below_threshold_silent_skip_interactive(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/research.md")
    called: list[str] = []
    warned: list[str] = []

    def confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        called.append(art.path)
        return SymlinkDecision(accept=True, target=target)

    # research(75) < threshold(80) → interactive silent skip: confirm NOT called, NO warning.
    offer_symlinks(
        root,
        [
            artifact(
                path="docs/research.md",
                kind="research",
                confidence=75,
                suggested_target="01-Requirement/02-Research/research.md",
            )
        ],
        confirm=confirm,
        auto_accept_threshold=80,
        warn=warned.append,
    )
    assert called == []
    assert warned == []
    assert not (root / MANIFEST_REL).exists()


def test_non_interactive_auto_accepts_at_or_above_threshold(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, "docs/architecture-2024.md")
    # confirm=None ⇒ non-interactive: confidence(85) ≥ threshold(80) → auto-accept.
    offer_symlinks(
        root,
        [artifact(confidence=85)],
        confirm=None,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    assert (root / ARCH_TARGET).is_symlink()
    assert (root / ARCH_TARGET).resolve() == src.resolve()
    assert len(read_manifest(root).mappings) == 1


def test_non_interactive_below_threshold_skips_with_warning(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/research.md")
    warned: list[str] = []
    offer_symlinks(
        root,
        [
            artifact(
                path="docs/research.md",
                kind="research",
                confidence=75,
                suggested_target="01-Requirement/02-Research/research.md",
            )
        ],
        confirm=None,
        auto_accept_threshold=80,
        warn=warned.append,
    )
    assert len(warned) == 1
    assert "research.md" in warned[0]
    assert not (root / MANIFEST_REL).exists()


def test_detect_only_kind_never_offered(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "README.md", "# proj\n")
    called: list[str] = []

    def confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        called.append(art.path)
        return SymlinkDecision(accept=True, target=target)

    # readme has empty suggested_target (detect-only, Story 3.2 D1) → never offered even at conf 90.
    offer_symlinks(
        root,
        [artifact(path="README.md", kind="readme", confidence=90, suggested_target="")],
        confirm=confirm,
        auto_accept_threshold=80,
    )
    assert called == []
    assert not (root / MANIFEST_REL).exists()

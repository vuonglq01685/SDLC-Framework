"""Story 3.6 — adopt re-run idempotency (Pass 2 + Pass 3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes import stamp, symlink_offer
from sdlc.adopt.passes.symlink_offer import SymlinkDecision
from sdlc.contracts.adopt_report import DetectedArtifact
from unit.adopt._symlink_offer_common import (
    ARCH_TARGET,
    accept_all,
    artifact,
    file_sha256,
    journal_entries,
    scaffold,
    write_source,
)

pytestmark = pytest.mark.unit

_OTHER_TARGET = "02-Architecture/02-System/OTHER.md"
_LOW_TARGET = "02-Architecture/02-System/LOW.md"


def test_rerun_skips_recorded_target_without_confirm(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, "docs/architecture-2024.md")
    journal = root / ".claude/state/journal.log"
    art = artifact()
    symlink_offer.offer_symlinks(
        root,
        [art],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=journal,
    )
    src_digest = file_sha256(src)
    prompts: list[str] = []

    def _should_not_prompt(_a: object, _t: str) -> SymlinkDecision:
        prompts.append("called")
        return SymlinkDecision(accept=True, target=ARCH_TARGET)

    symlink_offer.offer_symlinks(
        root,
        [art],
        confirm=_should_not_prompt,
        auto_accept_threshold=80,
        journal_path=journal,
    )
    assert prompts == []
    kinds = [e.kind for e in journal_entries(root)]
    assert kinds.count("adopt_re_run") == 1
    assert kinds.count("symlink_accepted") == 1
    assert file_sha256(src) == src_digest  # NFR-REL-6: source untouched across re-run


def test_partial_resume_informs_user_and_resumes_first_undecided(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src_a = write_source(root, "docs/architecture-2024.md")
    src_b = write_source(root, "docs/other.md", body="# Other\n")
    journal = root / ".claude/state/journal.log"
    art_a = artifact()
    art_b = artifact(path="docs/other.md", suggested_target=_OTHER_TARGET)

    # Partial first run: only A is decided/recorded.
    symlink_offer.offer_symlinks(
        root, [art_a], confirm=accept_all, auto_accept_threshold=80, journal_path=journal
    )
    a_digest, b_digest = file_sha256(src_a), file_sha256(src_b)

    warnings: list[str] = []
    confirmed: list[str] = []

    def _confirm(a: DetectedArtifact, target: str) -> SymlinkDecision:
        confirmed.append(a.path)
        return SymlinkDecision(accept=True, target=target)

    # Re-run with [A already decided, B un-decided].
    symlink_offer.offer_symlinks(
        root,
        [art_a, art_b],
        confirm=_confirm,
        auto_accept_threshold=80,
        journal_path=journal,
        warn=warnings.append,
    )

    # AC4: B (the first un-decided candidate) is resumed/adopted; A is skipped...
    assert (root / ARCH_TARGET).is_symlink()
    assert (root / _OTHER_TARGET).is_symlink()
    # ...the user is INFORMED A was already decided (AC4(iii))...
    assert any("already adopted" in w for w in warnings)
    # ...and the interactive confirm is NOT invoked for the already-recorded A (correction B).
    assert confirmed == ["docs/other.md"]
    assert [e.kind for e in journal_entries(root)].count("adopt_re_run") == 1
    assert file_sha256(src_a) == a_digest
    assert file_sha256(src_b) == b_digest


def test_rerun_emits_adopt_re_run_even_with_no_activity(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    write_source(root, "docs/low.md")
    journal = root / ".claude/state/journal.log"
    symlink_offer.offer_symlinks(
        root, [artifact()], confirm=accept_all, auto_accept_threshold=80, journal_path=journal
    )

    # Re-run whose only candidate is below threshold: new_adoptions == 0, skipped_existing == 0,
    # yet a prior manifest exists → D3(a) requires the adopt_re_run summary to still fire (P4).
    low = artifact(path="docs/low.md", confidence=10, suggested_target=_LOW_TARGET)
    symlink_offer.offer_symlinks(
        root, [low], confirm=accept_all, auto_accept_threshold=80, journal_path=journal
    )
    assert [e.kind for e in journal_entries(root)].count("adopt_re_run") == 1


def test_stamp_skips_existing_metadata_sidecar(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    journal = root / ".claude/state/journal.log"
    art = artifact()
    symlink_offer.offer_symlinks(
        root,
        [art],
        auto_accept_threshold=80,
        journal_path=journal,
    )
    stamp.mark_imported(root, [art], journal_path=journal)
    before = len(journal_entries(root))
    stamp.mark_imported(root, [art], journal_path=journal)
    after = len(journal_entries(root))
    assert after == before

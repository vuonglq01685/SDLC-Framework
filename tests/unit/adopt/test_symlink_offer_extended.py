"""Pass 2 symlink offer — conflict, idempotency, robustness (Story 3.3, AC4+)."""

from __future__ import annotations

import os
from pathlib import Path

from sdlc.adopt.passes.symlink_offer import SymlinkDecision, offer_symlinks
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks
from unit.adopt._symlink_offer_common import (
    ARCH_TARGET,
    JOURNAL_REL,
    MANIFEST_REL,
    accept_all,
    artifact,
    journal_entries,
    read_manifest,
    scaffold,
    write_source,
)

pytestmark = __import__("pytest").mark.unit

# --- AC4: conflict + idempotency -------------------------------------------------------------


def test_target_exists_real_file_skipped_and_warned(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    pre = root / ARCH_TARGET
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text("PRE-EXISTING REAL FILE\n", encoding="utf-8")
    warned: list[str] = []
    offer_symlinks(root, [artifact()], confirm=None, auto_accept_threshold=80, warn=warned.append)
    # not clobbered, not a symlink, not recorded.
    assert not pre.is_symlink()
    assert pre.read_text(encoding="utf-8") == "PRE-EXISTING REAL FILE\n"
    assert len(warned) == 1
    assert not (root / MANIFEST_REL).exists()


def test_target_symlink_pointing_elsewhere_skipped(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    other = write_source(root, "docs/other.md", "# other\n")
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(os.path.relpath(other, start=target.parent))
    warned: list[str] = []
    offer_symlinks(root, [artifact()], confirm=None, auto_accept_threshold=80, warn=warned.append)
    # still points at `other`, not rewired; not recorded.
    assert target.resolve() == other.resolve()
    assert len(warned) == 1
    assert not (root / MANIFEST_REL).exists()


def test_already_correct_symlink_is_idempotent_success(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    src = write_source(root, "docs/architecture-2024.md")
    target = root / ARCH_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(os.path.relpath(src, start=target.parent))
    # offering again must not raise; the already-correct symlink is recorded (AC4).
    offer_symlinks(
        root,
        [artifact()],
        confirm=None,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    assert target.is_symlink()
    assert target.resolve() == src.resolve()
    assert len(read_manifest(root).mappings) == 1


# --- AC6: source untouched -------------------------------------------------------------------


def test_source_bytes_unchanged_after_offer(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    body = "# Architecture\n\nADR-001\n"
    src = write_source(root, "docs/architecture-2024.md", body)
    before = src.read_bytes()
    offer_symlinks(root, [artifact()], confirm=accept_all, auto_accept_threshold=80)
    assert src.read_bytes() == before
    assert not src.is_symlink()  # the SOURCE is a real file, never replaced


# --- AC2: manifest is the frozen contract, written canonically -------------------------------


def test_manifest_is_valid_contract_with_trailing_newline(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(root, [artifact()], confirm=accept_all, auto_accept_threshold=80)
    raw = (root / MANIFEST_REL).read_bytes()
    assert raw.endswith(b"\n")
    AdoptedSymlinks.model_validate_json(raw.decode("utf-8"))  # parses as the frozen contract


def test_existing_manifest_mappings_are_preserved(tmp_path: Path) -> None:
    root = scaffold(tmp_path)
    # pre-seed a manifest with an unrelated prior mapping.
    prior = AdoptedSymlinks(
        mappings=(
            {
                "source": "docs/prd-old.md",
                "target": "01-Requirement/01-PRODUCT.md",
                "accepted_at": "2026-06-03T00:00:00.000Z",
                "kind": "prd",
            },
        )
    )
    (root / MANIFEST_REL).write_text(prior.model_dump_json(), encoding="utf-8")
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(root, [artifact()], confirm=accept_all, auto_accept_threshold=80)
    manifest = read_manifest(root)
    targets = {m.target for m in manifest.mappings}
    assert "01-Requirement/01-PRODUCT.md" in targets  # prior preserved
    assert ARCH_TARGET in targets  # new one added


# --- code-review patches: robustness beyond the explicit ACs ---------------------------------


def test_source_missing_creates_no_broken_symlink_and_warns(tmp_path: Path) -> None:
    """P1: a source that no longer exists (deleted after Pass 1) must not yield a broken symlink."""
    root = scaffold(tmp_path)
    # NOTE: no `write_source` — the detected source path does not exist on disk.
    warned: list[str] = []
    offer_symlinks(
        root,
        [artifact(path="docs/gone.md")],
        confirm=None,
        auto_accept_threshold=80,
        warn=warned.append,
        journal_path=root / JOURNAL_REL,
    )
    target = root / ARCH_TARGET
    assert not target.exists() and not target.is_symlink()  # no link to a non-existent source
    assert not (root / MANIFEST_REL).exists()  # nothing recorded
    assert len(warned) == 1 and "source no longer exists" in warned[0]
    assert [e for e in journal_entries(root) if e.kind == "symlink_accepted"] == []


def test_manifest_and_journal_share_one_timestamp(tmp_path: Path) -> None:
    """D1/P5: the manifest `accepted_at` and the journal `ts` for one symlink are identical."""
    root = scaffold(tmp_path)
    write_source(root, "docs/architecture-2024.md")
    offer_symlinks(
        root,
        [artifact()],
        confirm=accept_all,
        auto_accept_threshold=80,
        journal_path=root / JOURNAL_REL,
    )
    mapping = read_manifest(root).mappings[0]
    accepted = [e for e in journal_entries(root) if e.kind == "symlink_accepted"]
    assert len(accepted) == 1
    assert mapping.accepted_at == accepted[0].ts


def test_escaping_edited_target_skipped_and_otherartifact_still_processed(tmp_path: Path) -> None:
    """D2/P2: an injected `..`-escaping target skips that artifact (with a warning) and the pass
    continues — one bad artifact never aborts the whole offer."""
    root = scaffold(tmp_path)
    write_source(root, "docs/escape.md")
    good_src = write_source(root, "docs/architecture-2024.md")

    def confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        if art.path == "docs/escape.md":
            return SymlinkDecision(accept=True, target="../../../etc/passwd")  # escapes root
        return SymlinkDecision(accept=True, target=target)

    warned: list[str] = []
    offer_symlinks(
        root,
        [artifact(path="docs/escape.md"), artifact()],
        confirm=confirm,
        auto_accept_threshold=80,
        warn=warned.append,
    )
    assert any("escapes project root" in w for w in warned)
    # the second (valid) artifact was still symlinked + recorded
    assert (root / ARCH_TARGET).resolve() == good_src.resolve()
    targets = {m.target for m in read_manifest(root).mappings}
    assert targets == {ARCH_TARGET}


def test_os_error_on_oneartifact_does_not_abort_pass(tmp_path: Path) -> None:
    """D2: an OSError creating one symlink (parent path is a file) is fail-soft, not fatal."""
    root = scaffold(tmp_path)
    write_source(root, "docs/blocked.md")
    good_src = write_source(root, "docs/clean.md")
    # Make the first artifact's target un-creatable: its parent component is a real FILE, so
    # mkdir(parents=True) raises NotADirectoryError (an OSError).
    blocked_target = "blockdir/inner/BLOCKED.md"
    (root / "blockdir").write_text("i am a file, not a dir\n", encoding="utf-8")
    clean_target = "01-Requirement/01-PRODUCT.md"
    warned: list[str] = []
    offer_symlinks(
        root,
        [
            artifact(path="docs/blocked.md", suggested_target=blocked_target),
            artifact(
                path="docs/clean.md", kind="prd", confidence=90, suggested_target=clean_target
            ),
        ],
        confirm=None,
        auto_accept_threshold=80,
        warn=warned.append,
    )
    assert any("docs/blocked.md" in w for w in warned)  # the blocked one warned, did not crash
    assert (root / clean_target).resolve() == good_src.resolve()  # the clean one still created
    assert {m.target for m in read_manifest(root).mappings} == {clean_target}


def test_duplicate_targets_within_run_recorded_once(tmp_path: Path) -> None:
    """P7: two artifacts resolving to the same slot record once, with no misframed conflict."""
    root = scaffold(tmp_path)
    first = write_source(root, "docs/architecture-2024.md")
    write_source(root, "docs/architecture-old.md", "# old arch\n")
    warned: list[str] = []
    offer_symlinks(
        root,
        [
            artifact(path="docs/architecture-2024.md"),
            artifact(path="docs/architecture-old.md"),  # same ARCH_TARGET
        ],
        confirm=None,
        auto_accept_threshold=80,
        warn=warned.append,
    )
    mappings = read_manifest(root).mappings
    assert len(mappings) == 1  # first writer wins, second deduped
    assert (root / ARCH_TARGET).resolve() == first.resolve()
    assert not any("already exists" in w for w in warned)  # NOT framed as a pre-existing conflict


def test_corrupt_existing_manifest_warns_and_starts_fresh(tmp_path: Path) -> None:
    """P3: an unreadable prior manifest is warned about (not silently swallowed) and rebuilt."""
    root = scaffold(tmp_path)
    (root / MANIFEST_REL).write_text("{ this is not valid json", encoding="utf-8")
    write_source(root, "docs/architecture-2024.md")
    warned: list[str] = []
    offer_symlinks(
        root, [artifact()], confirm=accept_all, auto_accept_threshold=80, warn=warned.append
    )
    assert any("unreadable" in w for w in warned)
    # a fresh, valid manifest was written with the new mapping
    manifest = read_manifest(root)
    assert {m.target for m in manifest.mappings} == {ARCH_TARGET}


# --- AC7: boundary ---------------------------------------------------------------------------


def test_symlink_offer_imports_no_forbidden_layers() -> None:
    import sdlc.adopt.passes._symlink as helper_mod
    import sdlc.adopt.passes.symlink_offer as mod

    for module in (mod, helper_mod):
        src = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "import sdlc.cli",
            "from sdlc.cli",
            "sdlc.engine",
            "sdlc.dispatcher",
            "sdlc.runtime",
        ):
            assert forbidden not in src, f"{module.__name__} must not import {forbidden}"

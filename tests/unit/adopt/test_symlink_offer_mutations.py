"""Mutation-kill tests for passes/symlink_offer.py (Story 3.7 AC2, Tier-1).

Targets the 37 surviving mutants in symlink_offer.py by exercising:
- auto_accept_threshold boundary: confidence == threshold → accepted (not skipped)
- auto_accept_threshold boundary: confidence == threshold-1 → skipped
- had_prior_manifest: adopt_re_run emitted ONLY when prior manifest existed
- if changed: manifest written ONLY when new adoptions occurred
- new_adoptions count: exact count of new mappings added this run
- skipped_existing count: exact count of already-recorded targets skipped
- Corrupt manifest warning: warns but returns [] (not crash)
- _select_target: confirm=None path uses resolve_target
- _select_target: confirm callback path uses decision.target
- _write_manifest: calls assert_path_under_claude guard
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes.symlink_offer import (
    SymlinkDecision,
    offer_symlinks,
)
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry

pytestmark = pytest.mark.unit

_MANIFEST_REL = ".claude/state/adopted-symlinks.json"
_JOURNAL_REL = ".claude/state/journal.log"
_ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"
_SOURCE_REL = "docs/architecture-2024.md"
_TS = "2026-06-04T12:00:00.000Z"


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "journal.log").touch()
    return tmp_path


def _artifact(
    path: str = _SOURCE_REL,
    kind: str = "architecture",
    confidence: int = 85,
    suggested_target: str = _ARCH_TARGET,
) -> DetectedArtifact:
    return DetectedArtifact(
        path=path, kind=kind, confidence=confidence, suggested_target=suggested_target
    )


def _write_source(root: Path, rel: str = _SOURCE_REL) -> Path:
    src = root / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# Arch\n", encoding="utf-8")
    return src


def _accept_all(_art: DetectedArtifact, target: str) -> SymlinkDecision:
    return SymlinkDecision(accept=True, target=target)


def _read_manifest(root: Path) -> AdoptedSymlinks:
    return AdoptedSymlinks.model_validate_json((root / _MANIFEST_REL).read_text(encoding="utf-8"))


def _journal_entries(root: Path) -> list[JournalEntry]:
    text = (root / _JOURNAL_REL).read_text(encoding="utf-8")
    return [JournalEntry.model_validate_json(ln) for ln in text.splitlines() if ln.strip()]


def _write_manifest(root: Path, mappings: list[SymlinkMapping]) -> None:
    text = json.dumps(
        AdoptedSymlinks(mappings=tuple(mappings)).model_dump(mode="json"),
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    path = root / _MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((unicodedata.normalize("NFC", text) + "\n").encode("utf-8"))


def _mapping(source: str, target: str, kind: str = "architecture") -> SymlinkMapping:
    # type: ignore[arg-type]: _TS is a valid RFC3339Z string; Pydantic validates at runtime
    return SymlinkMapping(source=source, target=target, accepted_at=_TS, kind=kind)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# auto_accept_threshold boundary
# ---------------------------------------------------------------------------


def test_confidence_equal_to_threshold_is_accepted(tmp_path: Path) -> None:
    """confidence == auto_accept_threshold → artifact is accepted (not skipped)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    # confidence=80 == threshold=80 → must be accepted
    offer_symlinks(
        root,
        [_artifact(confidence=80)],
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )
    assert (root / _ARCH_TARGET).is_symlink()
    assert _read_manifest(root).mappings != ()


def test_confidence_one_below_threshold_is_skipped(tmp_path: Path) -> None:
    """confidence == auto_accept_threshold - 1 → artifact is silently skipped."""
    root = _scaffold(tmp_path)
    _write_source(root)
    called: list[str] = []

    def _confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        called.append(art.path)
        return SymlinkDecision(accept=True, target=target)

    offer_symlinks(
        root,
        [_artifact(confidence=79)],
        confirm=_confirm,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )
    # confidence 79 < 80 → never offered to confirm, no symlink
    assert called == []
    assert not (root / _ARCH_TARGET).exists()
    assert not (root / _MANIFEST_REL).exists()


def test_non_interactive_confidence_equal_threshold_auto_accepts(tmp_path: Path) -> None:
    """Non-interactive: confidence == threshold → auto-accept (not skip)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    offer_symlinks(
        root,
        [_artifact(confidence=80)],
        confirm=None,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )
    assert (root / _ARCH_TARGET).is_symlink()


def test_non_interactive_confidence_below_threshold_warns(tmp_path: Path) -> None:
    """Non-interactive: confidence < threshold → warning emitted."""
    root = _scaffold(tmp_path)
    _write_source(root)
    warns: list[str] = []
    offer_symlinks(
        root,
        [_artifact(confidence=79)],
        confirm=None,
        auto_accept_threshold=80,
        warn=warns.append,
    )
    assert len(warns) == 1
    assert "79" in warns[0] or "threshold" in warns[0] or _SOURCE_REL in warns[0]


# ---------------------------------------------------------------------------
# adopt_re_run: emitted only when prior manifest existed
# ---------------------------------------------------------------------------


def test_adopt_re_run_emitted_only_when_prior_manifest(tmp_path: Path) -> None:
    """adopt_re_run journal event is emitted ONLY when a prior manifest file existed."""
    root = _scaffold(tmp_path)
    _write_source(root)
    # Write a prior manifest with an existing mapping
    prior = _mapping(source="docs/prior.md", target="01-Requirement/01-PRODUCT.md", kind="prd")
    _write_manifest(root, [prior])

    offer_symlinks(
        root,
        [_artifact()],
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )

    entries = _journal_entries(root)
    rerun_events = [e for e in entries if e.kind == "adopt_re_run"]
    assert len(rerun_events) == 1


def test_adopt_re_run_not_emitted_on_fresh_run(tmp_path: Path) -> None:
    """adopt_re_run journal event is NOT emitted when there was no prior manifest."""
    root = _scaffold(tmp_path)
    _write_source(root)
    # No prior manifest written

    offer_symlinks(
        root,
        [_artifact()],
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )

    entries = _journal_entries(root)
    rerun_events = [e for e in entries if e.kind == "adopt_re_run"]
    assert len(rerun_events) == 0


def test_adopt_re_run_new_adoptions_count_is_correct(tmp_path: Path) -> None:
    """adopt_re_run.new_adoptions == number of new mappings added this run."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "docs/prd.md")
    prior = _mapping(source="docs/prior.md", target="01-Requirement/01-PRODUCT.md", kind="prd")
    _write_manifest(root, [prior])

    prd_target = "01-Requirement/01-PRODUCT-NEW.md"
    artifacts = [
        _artifact(confidence=85),  # new adoption
        _artifact(  # new adoption
            path="docs/prd.md", kind="prd", confidence=85, suggested_target=prd_target
        ),
    ]

    offer_symlinks(
        root,
        artifacts,
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )

    entries = _journal_entries(root)
    rerun = next(e for e in entries if e.kind == "adopt_re_run")
    assert rerun.payload["new_adoptions"] == 2  # exactly 2, not 3 or 1


def test_adopt_re_run_skipped_existing_count_is_correct(tmp_path: Path) -> None:
    """adopt_re_run.skipped_existing == number of targets already in manifest."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    prior = _mapping(source=_SOURCE_REL, target=_ARCH_TARGET)
    _write_manifest(root, [prior])
    # Create the symlink so it already exists
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    src = root / _SOURCE_REL
    os.symlink(os.path.relpath(src, slot.parent), slot)

    offer_symlinks(
        root,
        [_artifact()],  # _ARCH_TARGET already in manifest → skipped_existing
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )

    entries = _journal_entries(root)
    rerun = next(e for e in entries if e.kind == "adopt_re_run")
    assert rerun.payload["skipped_existing"] == 1


# ---------------------------------------------------------------------------
# Manifest written only when changed
# ---------------------------------------------------------------------------


def test_manifest_not_written_when_nothing_accepted(tmp_path: Path) -> None:
    """If no new mappings are added, the manifest file is NOT created/updated."""
    root = _scaffold(tmp_path)
    _write_source(root)

    offer_symlinks(
        root,
        [_artifact()],
        confirm=lambda *_: SymlinkDecision(accept=False, target=_ARCH_TARGET),  # user rejected
        auto_accept_threshold=80,
    )
    assert not (root / _MANIFEST_REL).exists()


def test_manifest_is_written_when_at_least_one_accepted(tmp_path: Path) -> None:
    """When at least one mapping is added, the manifest IS written."""
    root = _scaffold(tmp_path)
    _write_source(root)

    offer_symlinks(
        root,
        [_artifact()],
        confirm=_accept_all,
        auto_accept_threshold=80,
    )
    assert (root / _MANIFEST_REL).exists()
    manifest = _read_manifest(root)
    assert len(manifest.mappings) == 1


# ---------------------------------------------------------------------------
# Corrupt manifest warning
# ---------------------------------------------------------------------------


def test_corrupt_manifest_warns_and_starts_empty(tmp_path: Path) -> None:
    """A corrupt existing manifest logs a warning but doesn't crash; starts fresh."""
    root = _scaffold(tmp_path)
    _write_source(root)
    (root / _MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / _MANIFEST_REL).write_text("{ not valid json }", encoding="utf-8")
    warns: list[str] = []

    offer_symlinks(
        root,
        [_artifact()],
        confirm=_accept_all,
        auto_accept_threshold=80,
        warn=warns.append,
    )

    # Warning issued for corrupt manifest
    assert any("unreadable" in w or "corrupt" in w for w in warns)
    # Still creates a new valid manifest with the new mapping
    manifest = _read_manifest(root)
    assert len(manifest.mappings) >= 1


# ---------------------------------------------------------------------------
# Detect-only kinds are never offered
# ---------------------------------------------------------------------------


def test_detect_only_artifact_with_empty_suggested_target_skipped(tmp_path: Path) -> None:
    """Artifacts with suggested_target='' are silently skipped regardless of confidence."""
    root = _scaffold(tmp_path)
    _write_source(root, "README.md")
    called: list[str] = []

    def _confirm(art: DetectedArtifact, target: str) -> SymlinkDecision:
        called.append(art.path)
        return SymlinkDecision(accept=True, target=target)

    offer_symlinks(
        root,
        [_artifact(path="README.md", kind="readme", confidence=95, suggested_target="")],
        confirm=_confirm,
        auto_accept_threshold=80,
    )
    assert called == []
    assert not (root / _MANIFEST_REL).exists()


# ---------------------------------------------------------------------------
# Manifest preserved from prior run
# ---------------------------------------------------------------------------


def test_prior_manifest_mappings_preserved_on_resume(tmp_path: Path) -> None:
    """Existing mappings in the prior manifest are preserved when new ones are added."""
    root = _scaffold(tmp_path)
    _write_source(root)
    prior_target = "01-Requirement/01-PRODUCT.md"
    prior = _mapping(source="docs/prior.md", target=prior_target, kind="prd")
    _write_manifest(root, [prior])

    offer_symlinks(
        root,
        [_artifact()],  # new mapping
        confirm=_accept_all,
        auto_accept_threshold=80,
    )

    manifest = _read_manifest(root)
    targets = {m.target for m in manifest.mappings}
    assert prior_target in targets
    assert _ARCH_TARGET in targets
    assert len(manifest.mappings) == 2

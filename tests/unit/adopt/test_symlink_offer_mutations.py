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
    _manifest_bytes,
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
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
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


# ---------------------------------------------------------------------------
# _manifest_bytes: canonical JSON form (sort_keys / ensure_ascii=False / compact)
# ---------------------------------------------------------------------------


def test_manifest_bytes_is_canonical_sorted_compact_utf8() -> None:
    """`_manifest_bytes` emits sorted keys, raw UTF-8, and compact separators."""
    manifest = AdoptedSymlinks(mappings=(_mapping(source="docs/aö.md", target="t/B.md"),))
    out = _manifest_bytes(manifest)

    # ensure_ascii=False → raw UTF-8 for ö (kills ensure_ascii=True).
    assert "aö".encode() in out
    assert out.count("ö".encode()) == 1
    # separators=(",", ":") → no padding (kills separators=None / dropped).
    assert b", " not in out
    assert b": " not in out
    # sort_keys=True → nested mapping keys in lexicographic order (kills sort_keys=False / None).
    text = out.decode()
    assert (
        text.index('"accepted_at"')
        < text.index('"kind"')
        < text.index('"source"')
        < text.index('"target"')
    )
    assert out.endswith(b"\n")
    assert json.loads(out)["mappings"][0]["source"] == "docs/aö.md"


# ---------------------------------------------------------------------------
# Corrupt-manifest warning carries the full "recoverable from the journal" tail
# ---------------------------------------------------------------------------


def test_corrupt_manifest_warning_mentions_journal_recoverable(tmp_path: Path) -> None:
    """The unreadable-manifest warning ends with the exact journal-recoverable reassurance."""
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
    assert any(w.endswith("(prior mappings remain recoverable from the journal)") for w in warns)


# ---------------------------------------------------------------------------
# Trailing-slash target → source basename appended (artifact.path is forwarded)
# ---------------------------------------------------------------------------

_RESEARCH_SLOT = "01-Requirement/02-Research/"
_RESEARCH_SOURCE = "docs/research-2024.md"
_RESEARCH_TARGET = "01-Requirement/02-Research/research-2024.md"


def test_trailing_slash_target_uses_source_basename_non_interactive(tmp_path: Path) -> None:
    """Non-interactive: a directory-style slot lands at <slot>/<source-basename>."""
    root = _scaffold(tmp_path)
    _write_source(root, _RESEARCH_SOURCE)
    art = _artifact(path=_RESEARCH_SOURCE, kind="research", suggested_target=_RESEARCH_SLOT)
    offer_symlinks(
        root, [art], confirm=None, auto_accept_threshold=80, journal_path=root / _JOURNAL_REL
    )
    assert (root / _RESEARCH_TARGET).is_symlink()
    assert _RESEARCH_TARGET in {m.target for m in _read_manifest(root).mappings}


def test_trailing_slash_target_uses_source_basename_interactive(tmp_path: Path) -> None:
    """Interactive: accepting a directory-style slot still appends the source basename."""
    root = _scaffold(tmp_path)
    _write_source(root, _RESEARCH_SOURCE)
    art = _artifact(path=_RESEARCH_SOURCE, kind="research", suggested_target=_RESEARCH_SLOT)
    offer_symlinks(
        root,
        [art],
        confirm=_accept_all,
        auto_accept_threshold=80,
        journal_path=root / _JOURNAL_REL,
    )
    assert (root / _RESEARCH_TARGET).is_symlink()


# ---------------------------------------------------------------------------
# Loop continues past skips (continue, not break) + exact skipped_existing count
# ---------------------------------------------------------------------------


def test_below_threshold_skip_does_not_halt_later_artifacts(tmp_path: Path) -> None:
    """A below-threshold skip must `continue`, not `break` — later artifacts still get offered."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/low.md")
    _write_source(root, _SOURCE_REL)
    low = _artifact(path="docs/low.md", confidence=10, suggested_target="01-X/LOW.md")
    high = _artifact(path=_SOURCE_REL, confidence=95, suggested_target=_ARCH_TARGET)
    offer_symlinks(
        root, [low, high], confirm=None, auto_accept_threshold=80, journal_path=root / _JOURNAL_REL
    )
    assert (root / _ARCH_TARGET).is_symlink()  # the high-confidence one was still processed
    assert not (root / "01-X/LOW.md").exists()


def test_two_already_recorded_skipped_then_new_adopted(tmp_path: Path) -> None:
    """Two already-recorded targets → skipped_existing == 2 (+=, not =1), loop continues to new."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "docs/p2.md")
    _write_source(root, "docs/new.md")
    t1, t2 = _ARCH_TARGET, "01-Requirement/01-PRODUCT.md"
    _write_manifest(
        root,
        [
            _mapping(source=_SOURCE_REL, target=t1),
            _mapping(source="docs/p2.md", target=t2, kind="prd"),
        ],
    )
    for src_rel, tgt in ((_SOURCE_REL, t1), ("docs/p2.md", t2)):
        slot = root / tgt
        slot.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(root / src_rel, slot.parent), slot)

    new_target = "01-Requirement/02-RESEARCH.md"
    arts = [
        _artifact(path=_SOURCE_REL, suggested_target=t1),  # resolved_default already recorded
        _artifact(path="docs/p2.md", kind="prd", suggested_target=t2),  # already recorded
        _artifact(path="docs/new.md", kind="research", suggested_target=new_target),  # new
    ]
    offer_symlinks(
        root, arts, confirm=None, auto_accept_threshold=80, journal_path=root / _JOURNAL_REL
    )

    rerun = next(e for e in _journal_entries(root) if e.kind == "adopt_re_run")
    assert rerun.payload["skipped_existing"] == 2
    assert (root / new_target).is_symlink()


def test_edit_to_already_recorded_target_skips_warns_and_continues(tmp_path: Path) -> None:
    """An edit onto an already-recorded target skips+warns (final_target dedup) and keeps going."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "docs/e1.md")
    _write_source(root, "docs/e2.md")
    _write_source(root, "docs/new.md")
    _write_manifest(root, [_mapping(source=_SOURCE_REL, target=_ARCH_TARGET)])
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(root / _SOURCE_REL, slot.parent), slot)

    new_target = "01-Requirement/01-PRODUCT.md"

    def _confirm(art: DetectedArtifact, _suggested: str) -> SymlinkDecision:
        if art.path in ("docs/e1.md", "docs/e2.md"):
            return SymlinkDecision(accept=True, target=_ARCH_TARGET)  # edit onto recorded slot
        return SymlinkDecision(accept=True, target=new_target)

    warns: list[str] = []
    arts = [
        _artifact(path="docs/e1.md", suggested_target="01-X/E1.md"),
        _artifact(path="docs/e2.md", suggested_target="01-X/E2.md"),
        _artifact(path="docs/new.md", kind="prd", suggested_target=new_target),
    ]
    offer_symlinks(
        root,
        arts,
        confirm=_confirm,
        auto_accept_threshold=80,
        warn=warns.append,
        journal_path=root / _JOURNAL_REL,
    )

    rerun = next(e for e in _journal_entries(root) if e.kind == "adopt_re_run")
    assert rerun.payload["skipped_existing"] == 2  # final_target dedup hit twice (+=, not =1)
    assert any(f"already adopted (target {_ARCH_TARGET})" in w for w in warns)
    assert (root / new_target).is_symlink()  # the genuine-new artifact still processed


def test_rejected_artifact_does_not_halt_later_artifacts(tmp_path: Path) -> None:
    """A rejected offer (_select_target → None) must `continue`, not `break`."""
    root = _scaffold(tmp_path)
    _write_source(root, "docs/rej.md")
    _write_source(root, _SOURCE_REL)

    def _confirm(art: DetectedArtifact, suggested: str) -> SymlinkDecision:
        if art.path == "docs/rej.md":
            return SymlinkDecision(accept=False, target=suggested)  # reject → _select_target None
        return SymlinkDecision(accept=True, target=suggested)

    arts = [
        _artifact(path="docs/rej.md", suggested_target="01-X/REJ.md"),
        _artifact(path=_SOURCE_REL, suggested_target=_ARCH_TARGET),
    ]
    offer_symlinks(
        root, arts, confirm=_confirm, auto_accept_threshold=80, journal_path=root / _JOURNAL_REL
    )
    assert (root / _ARCH_TARGET).is_symlink()  # the accepted artifact after the reject was reached
    assert not (root / "01-X/REJ.md").exists()

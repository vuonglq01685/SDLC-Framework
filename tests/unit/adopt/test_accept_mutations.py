"""Mutation-kill tests for passes/_accept.py (Story 3.7 AC2, Tier-1).

Targets the 107 surviving mutants in _accept.py by exercising:
- Exact return-value contracts (True/False from accept_one_artifact)
- Recording side-effects (mappings list growth, recorded_targets set growth)
- Journal event payloads (source, target, kind, ts field precision)
- Shared-timestamp invariant between symlink_replaced + symlink_accepted events
- _MAX_DIFFERENT_TARGET_ATTEMPTS = 8 boundary
- different_target_attempts counter increments (reset: each call is independent)
- ConflictKind dispatch correctness (REAL_FILE vs OTHER_SYMLINK)
- _do_backup_replace coupling: create failure → restores backup
- Duplicate-target early-return (return False, not True)
- Source-missing early-return (return False without adding to mappings)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt.passes import _accept, _symlink
from sdlc.adopt.passes._accept import (
    ConflictContext,
    ConflictDecision,
    ConflictKind,
    accept_one_artifact,
    append_adopt_rerun_event,
)
from sdlc.adopt.passes._symlink import SymlinkOutcome
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import SymlinkMapping
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_ARCH_TARGET = "02-Architecture/02-System/ARCHITECTURE.md"
_SOURCE_REL = "docs/architecture-2024.md"
_TS = "2026-06-04T12:00:00.000Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _write_source(root: Path, rel: str = _SOURCE_REL, body: str = "# Arch\n") -> Path:
    src = root / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body, encoding="utf-8")
    return src


def _journal_entries(root: Path) -> list[JournalEntry]:
    path = root / ".claude/state/journal.log"
    lines = path.read_text().splitlines()
    return [JournalEntry.model_validate_json(ln) for ln in lines if ln.strip()]


def _mapping(
    source: str = _SOURCE_REL,
    target: str = _ARCH_TARGET,
    kind: str = "architecture",
) -> SymlinkMapping:
    return SymlinkMapping(source=source, target=target, accepted_at=_TS, kind=kind)  # type: ignore[arg-type]


def _no_conflict(*_: object) -> ConflictDecision:
    return ConflictDecision(action="skip")


# ---------------------------------------------------------------------------
# Return-value contracts
# ---------------------------------------------------------------------------


def test_accept_returns_true_on_success(tmp_path: Path) -> None:
    """accept_one_artifact returns True when symlink is created (return value mutation)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=root / ".claude/state/journal.log",
        conflict=_no_conflict,
        warn=None,
    )
    assert result is True


def test_accept_returns_false_when_target_already_recorded(tmp_path: Path) -> None:
    """accept_one_artifact returns False without adding to mappings when target pre-recorded."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = {_ARCH_TARGET}  # pre-recorded

    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=root / ".claude/state/journal.log",
        conflict=_no_conflict,
        warn=None,
    )
    assert result is False
    assert len(mappings) == 0  # no mutation of mappings on False return


def test_accept_returns_false_when_source_missing(tmp_path: Path) -> None:
    """accept_one_artifact returns False (source missing) without touching mappings."""
    root = _scaffold(tmp_path)
    # Deliberately do NOT write the source file
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=root / ".claude/state/journal.log",
        conflict=_no_conflict,
        warn=warns.append,
    )
    assert result is False
    assert len(mappings) == 0


# ---------------------------------------------------------------------------
# Recording side-effects
# ---------------------------------------------------------------------------


def test_accept_appends_exactly_one_mapping(tmp_path: Path) -> None:
    """accept_one_artifact appends exactly one SymlinkMapping to mappings on success."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=root / ".claude/state/journal.log",
        conflict=_no_conflict,
        warn=None,
    )
    assert len(mappings) == 1
    m = mappings[0]
    assert m.source == _SOURCE_REL
    assert m.target == _ARCH_TARGET
    assert m.kind == "architecture"


def test_accept_adds_target_to_recorded_set(tmp_path: Path) -> None:
    """accept_one_artifact adds target to recorded_targets so duplicates are blocked."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=root / ".claude/state/journal.log",
        conflict=_no_conflict,
        warn=None,
    )
    assert _ARCH_TARGET in recorded


def test_second_call_with_same_target_returns_false(tmp_path: Path) -> None:
    """After first successful accept, second call with same target returns False."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()
    journal = root / ".claude/state/journal.log"
    kw = dict(journal_path=journal, conflict=_no_conflict, warn=None)

    first = accept_one_artifact(root, _artifact(), _ARCH_TARGET, mappings, recorded, **kw)
    assert first is True

    second = accept_one_artifact(root, _artifact(), _ARCH_TARGET, mappings, recorded, **kw)
    assert second is False
    # mappings must NOT have grown a second time
    assert len(mappings) == 1


# ---------------------------------------------------------------------------
# Journal event payloads
# ---------------------------------------------------------------------------


def test_journal_symlink_accepted_has_correct_payload(tmp_path: Path) -> None:
    """symlink_accepted journal entry carries exact source/target/kind fields."""
    root = _scaffold(tmp_path)
    _write_source(root)
    journal = root / ".claude/state/journal.log"
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root,
        _artifact(kind="architecture"),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=journal,
        conflict=_no_conflict,
        warn=None,
    )

    accepted = [e for e in _journal_entries(root) if e.kind == "symlink_accepted"]
    assert len(accepted) == 1
    payload = accepted[0].payload
    assert payload["source"] == _SOURCE_REL
    assert payload["target"] == _ARCH_TARGET
    assert payload["kind"] == "architecture"


def test_journal_symlink_accepted_ts_ends_with_z(tmp_path: Path) -> None:
    """symlink_accepted journal entry has a UTC timestamp (ends with Z)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    journal = root / ".claude/state/journal.log"
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=journal, conflict=_no_conflict, warn=None,
    )

    accepted = [e for e in _journal_entries(root) if e.kind == "symlink_accepted"]
    assert accepted[0].ts.endswith("Z")


def test_journal_event_schema_version_is_one(tmp_path: Path) -> None:
    """All journal entries emitted by _accept carry schema_version=1."""
    root = _scaffold(tmp_path)
    _write_source(root)
    journal = root / ".claude/state/journal.log"
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=journal, conflict=_no_conflict, warn=None,
    )

    for entry in _journal_entries(root):
        assert entry.schema_version == 1


def test_journal_event_after_hash_is_zero_sentinel(tmp_path: Path) -> None:
    """symlink_accepted entry uses event-only zero hash (no content written to source)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    journal = root / ".claude/state/journal.log"
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=journal, conflict=_no_conflict, warn=None,
    )

    zero = "sha256:" + "0" * 64
    for entry in _journal_entries(root):
        assert entry.after_hash == zero
        assert entry.before_hash is None


# ---------------------------------------------------------------------------
# Other-symlink conflict — shared timestamp invariant
# ---------------------------------------------------------------------------


def test_replace_other_symlink_journals_replaced_and_accepted_shared_ts(tmp_path: Path) -> None:
    """symlink_replaced + symlink_accepted share exactly one timestamp (single-ts cross-ref)."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/other.md", "# Other\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/other.md", slot)
    journal = root / ".claude/state/journal.log"

    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    def _replace(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        assert ctx.kind is ConflictKind.OTHER_SYMLINK
        return ConflictDecision(action="replace")

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=journal, conflict=_replace, warn=None,
    )

    entries = _journal_entries(root)
    replaced = [e for e in entries if e.kind == "symlink_replaced"]
    accepted = [e for e in entries if e.kind == "symlink_accepted"]
    assert len(replaced) == 1
    assert len(accepted) == 1
    # The shared-timestamp invariant: both events must have IDENTICAL ts.
    assert replaced[0].ts == accepted[0].ts


def test_replace_other_symlink_replaced_payload(tmp_path: Path) -> None:
    """symlink_replaced payload carries target and old_source exactly."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/old.md", "# Old\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/old.md", slot)
    journal = root / ".claude/state/journal.log"

    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=journal,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=None,
    )

    entries = _journal_entries(root)
    replaced = next(e for e in entries if e.kind == "symlink_replaced")
    assert replaced.payload["target"] == _ARCH_TARGET
    assert replaced.payload["old_source"] == "legacy/old.md"


# ---------------------------------------------------------------------------
# ConflictKind dispatch
# ---------------------------------------------------------------------------


def test_real_file_conflict_calls_conflict_with_real_file_kind(tmp_path: Path) -> None:
    """When target is a real file, conflict callback receives ConflictKind.REAL_FILE."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    journal = root / ".claude/state/journal.log"

    kinds_seen: list[ConflictKind] = []

    def _capture(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        kinds_seen.append(ctx.kind)
        return ConflictDecision(action="skip")

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, [], set(),
        journal_path=journal, conflict=_capture, warn=None,
    )
    assert ConflictKind.REAL_FILE in kinds_seen


def test_other_symlink_conflict_calls_conflict_with_other_symlink_kind(tmp_path: Path) -> None:
    """When target is a symlink pointing elsewhere, conflict callback gets OTHER_SYMLINK."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "other/src.md", "# Other\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../other/src.md", slot)
    journal = root / ".claude/state/journal.log"

    kinds_seen: list[ConflictKind] = []

    def _capture(_a: DetectedArtifact, _t: str, ctx: ConflictContext) -> ConflictDecision:
        kinds_seen.append(ctx.kind)
        return ConflictDecision(action="skip")

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, [], set(),
        journal_path=journal, conflict=_capture, warn=None,
    )
    assert ConflictKind.OTHER_SYMLINK in kinds_seen


# ---------------------------------------------------------------------------
# _MAX_DIFFERENT_TARGET_ATTEMPTS boundary
# ---------------------------------------------------------------------------


def test_unsafe_different_target_is_bounded_at_eight_attempts(tmp_path: Path) -> None:
    """Unsafe `different_target` responses are retried at most 8 times, then skipped."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    journal = root / ".claude/state/journal.log"

    call_count = 0
    warns: list[str] = []

    def _always_unsafe(_a: DetectedArtifact, _t: str, _c: ConflictContext) -> ConflictDecision:
        nonlocal call_count
        call_count += 1
        return ConflictDecision(action="different_target", target="../escape.md")

    result = accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, [], set(),
        journal_path=journal, conflict=_always_unsafe, warn=warns.append,
    )

    assert result is False
    # The call_count ≤ _MAX_DIFFERENT_TARGET_ATTEMPTS (8) — not infinite loop
    assert call_count <= 8
    assert any("too many" in w or "attempts" in w for w in warns)


def test_different_target_attempts_at_seven_does_not_stop(tmp_path: Path) -> None:
    """At 7 unsafe `different_target` responses, the loop does NOT yet give up."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    journal = root / ".claude/state/journal.log"

    call_count = 0
    warns: list[str] = []

    def _unsafe_then_skip(_a: DetectedArtifact, _t: str, _c: ConflictContext) -> ConflictDecision:
        nonlocal call_count
        call_count += 1
        if call_count < 8:
            return ConflictDecision(action="different_target", target="../escape.md")
        # On the 8th call, accept a safe target
        return ConflictDecision(action="skip")

    accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, [], set(),
        journal_path=journal, conflict=_unsafe_then_skip, warn=warns.append,
    )
    # Should have made it to at least 7 calls without stopping
    assert call_count >= 7


# ---------------------------------------------------------------------------
# backup_replace coupling: create failure restores backup
# ---------------------------------------------------------------------------


def test_backup_replace_create_failure_restores_real_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When create_relative_symlink raises AFTER backup, the real file is restored."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    real_content = "must survive\n"
    slot.write_text(real_content, encoding="utf-8")
    journal = root / ".claude/state/journal.log"

    real_create = _symlink.create_relative_symlink

    def _fail_after_backup(r: Path, src_rel: str, tgt_rel: str) -> SymlinkOutcome:
        # Only fail on the post-backup create (slot empty = backup already moved it)
        candidate = r / tgt_rel
        if not candidate.exists() and not candidate.is_symlink():
            raise AdoptError("simulated post-backup create failure", details={})
        return real_create(r, src_rel, tgt_rel)

    monkeypatch.setattr(_accept, "create_relative_symlink", _fail_after_backup)
    warns: list[str] = []

    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, set(),
        journal_path=journal,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warns.append,
    )

    # File must be restored, not left in backup
    assert slot.read_text(encoding="utf-8") == real_content
    assert not slot.is_symlink()
    assert result is False
    assert len(mappings) == 0  # nothing recorded on failure
    assert any("restor" in w.lower() for w in warns)


# ---------------------------------------------------------------------------
# No-journal path (journal_path=None) — no crash, just silent
# ---------------------------------------------------------------------------


def test_accept_without_journal_path_does_not_crash(tmp_path: Path) -> None:
    """accept_one_artifact functions when journal_path=None (test/no-op mode)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    mappings: list[SymlinkMapping] = []
    recorded: set[str] = set()

    result = accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, recorded,
        journal_path=None,
        conflict=_no_conflict,
        warn=None,
    )
    assert result is True
    assert len(mappings) == 1


# ---------------------------------------------------------------------------
# append_adopt_rerun_event
# ---------------------------------------------------------------------------


def test_adopt_rerun_event_payload_fields(tmp_path: Path) -> None:
    """append_adopt_rerun_event writes adopt_re_run entry with correct fields."""
    root = _scaffold(tmp_path)
    journal = root / ".claude/state/journal.log"

    append_adopt_rerun_event(
        journal,
        new_adoptions=3,
        skipped_existing=7,
        ts="2026-06-04T12:00:00.000Z",
    )

    entries = _journal_entries(root)
    assert len(entries) == 1
    e = entries[0]
    assert e.kind == "adopt_re_run"
    assert e.payload["new_adoptions"] == 3
    assert e.payload["skipped_existing"] == 7


def test_adopt_rerun_event_new_adoptions_zero(tmp_path: Path) -> None:
    """append_adopt_rerun_event correctly records new_adoptions=0 (not 1 or -1)."""
    root = _scaffold(tmp_path)
    journal = root / ".claude/state/journal.log"

    append_adopt_rerun_event(
        journal, new_adoptions=0, skipped_existing=5, ts="2026-06-04T12:00:00.000Z"
    )

    entries = _journal_entries(root)
    assert entries[0].payload["new_adoptions"] == 0
    assert entries[0].payload["skipped_existing"] == 5


# ---------------------------------------------------------------------------
# accept_one_artifact: no warn → no crash when None passed
# ---------------------------------------------------------------------------


def test_accept_with_warn_none_does_not_crash_on_missing_source(tmp_path: Path) -> None:
    """With warn=None and missing source, accept_one_artifact silently returns False."""
    root = _scaffold(tmp_path)
    result = accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, [], set(),
        journal_path=None, conflict=None, warn=None,
    )
    assert result is False


def test_accept_with_skip_conflict_decision_returns_false(tmp_path: Path) -> None:
    """ConflictDecision(action='skip') causes accept_one_artifact to return False."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")

    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root, _artifact(), _ARCH_TARGET, mappings, set(),
        journal_path=root / ".claude/state/journal.log",
        conflict=lambda *_: ConflictDecision(action="skip"),
        warn=None,
    )
    assert result is False
    assert len(mappings) == 0

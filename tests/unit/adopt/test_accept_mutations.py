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
    # type: ignore[arg-type]: _TS is a valid RFC3339Z string; Pydantic validates at runtime
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=journal,
        conflict=_no_conflict,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=journal,
        conflict=_no_conflict,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=journal,
        conflict=_no_conflict,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
        journal_path=journal,
        conflict=_replace,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=journal,
        conflict=_capture,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=journal,
        conflict=_capture,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=journal,
        conflict=_always_unsafe,
        warn=warns.append,
    )

    assert result is False
    # 8 different-target attempts are consumed (different_target_attempts 0→8); the bound check
    # `>= _MAX_DIFFERENT_TARGET_ATTEMPTS` sits AFTER the conflict callback, so the 9th prompt's
    # answer is what trips "too many … skipping". The callback is therefore invoked exactly 9
    # times — pinning the boundary kills the `_MAX` 8→7 (would give 8) and 8→9 (would give 10).
    assert call_count == 9
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
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=journal,
        conflict=_unsafe_then_skip,
        warn=warns.append,
    )
    # Exactly 8 calls (1-7 return different_target, 8th returns skip) - not stopped early
    assert call_count == 8


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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        recorded,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=None,
        warn=None,
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
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
        journal_path=root / ".claude/state/journal.log",
        conflict=lambda *_: ConflictDecision(action="skip"),
        warn=None,
    )
    assert result is False
    assert len(mappings) == 0


# ---------------------------------------------------------------------------
# Exact warn-message contracts (mutation-kill). `_warn_skip` emits
# f"skipping {path}: {reason}"; asserting the FULL string on each call site
# kills the path->None, reason->"XX..XX"/UPPER/None, warn=warn->warn=None and
# argument-drop mutants on that line in a single assertion. Each also pins the
# `return False` (vs True) on its branch.
# ---------------------------------------------------------------------------

_SKIP_PREFIX = f"skipping {_SOURCE_REL}: "


def test_warn_exact_source_missing(tmp_path: Path) -> None:
    """Source-missing branch warns the exact reason and returns False."""
    root = _scaffold(tmp_path)  # deliberately no source written
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=_no_conflict,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "source no longer exists (no symlink created)"]


def test_warn_exact_real_file_conflict_without_callback(tmp_path: Path) -> None:
    """Real-file conflict + conflict=None warns the exact reason."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=None,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "target already exists as a real file"]


def test_warn_exact_other_symlink_conflict_without_callback(tmp_path: Path) -> None:
    """Other-symlink conflict + conflict=None warns the exact reason."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/other.md", "# Other\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/other.md", slot)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=None,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "target already occupied by a different symlink"]


def test_warn_exact_initial_target_escapes_root(tmp_path: Path) -> None:
    """An initial target outside the root warns the exact escape reason."""
    root = _scaffold(tmp_path)
    _write_source(root)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        "../escape.md",
        [],
        set(),
        journal_path=None,
        conflict=_no_conflict,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "unsafe target '../escape.md' escapes project root"]


def test_warn_exact_backup_replace_invalid_for_other_symlink(tmp_path: Path) -> None:
    """`backup_replace` on a different-symlink conflict warns the exact reason."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/other.md", "# Other\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/other.md", slot)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "backup-and-replace is only valid for a real-file conflict"]


def test_warn_exact_replace_invalid_for_real_file(tmp_path: Path) -> None:
    """`replace` on a real-file conflict warns the exact reason."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "replace is only valid for a different-symlink conflict"]


def test_warn_exact_too_many_attempts_and_reprompt(tmp_path: Path) -> None:
    """Always-unsafe different_target yields 8 exact re-prompt warns then the exact give-up."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="different_target", target="../escape.md"),
        warn=warns.append,
    )
    assert result is False
    reprompt = _SKIP_PREFIX + "unsafe target '../escape.md' escapes project root; re-prompting"
    assert warns.count(reprompt) == 8
    assert warns[-1] == _SKIP_PREFIX + "too many different-target attempts; skipping"


def test_different_target_trailing_slash_uses_artifact_basename(tmp_path: Path) -> None:
    """different_target with a trailing slash resolves the filename from artifact.path
    (kills resolve_target's source-arg -> None mutation, which would crash on basename(None))."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)  # basename architecture-2024.md
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="different_target", target="docs/dest/"),
        warn=None,
    )
    assert result is True
    assert mappings[0].target == "docs/dest/architecture-2024.md"


def test_outcome_for_target_escape_returns_adopt_error_exact(tmp_path: Path) -> None:
    """_outcome_for_target returns an AdoptError with exact message + details for an
    escaping target (kills the details-dict key/value and message string mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    outcome = _accept._outcome_for_target(root, _artifact(), "../escape.md")
    assert isinstance(outcome, AdoptError)
    assert outcome.message == "adopt refuses a symlink target outside the project root"
    assert outcome.details == {"target": "../escape.md"}


def test_conflict_callback_receives_real_artifact_and_target(tmp_path: Path) -> None:
    """The conflict callback is invoked with the real artifact + target_rel
    (kills the artifact->None and target_rel->None argument mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    seen: list[tuple[object, object]] = []

    def _capture(a: DetectedArtifact, t: str, _c: ConflictContext) -> ConflictDecision:
        seen.append((a, t))
        return ConflictDecision(action="skip")

    accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=_capture,
        warn=None,
    )
    assert len(seen) == 1
    artifact_arg, target_arg = seen[0]
    assert isinstance(artifact_arg, DetectedArtifact)
    assert artifact_arg.path == _SOURCE_REL
    assert target_arg == _ARCH_TARGET


def test_skip_decision_is_clean_no_warn(tmp_path: Path) -> None:
    """action='skip' returns False with NO warning (kills the "skip" string-literal
    mutations, which would fall through to the replace path and emit a warn)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="skip"),
        warn=warns.append,
    )
    assert result is False
    assert warns == []


def test_unexpected_symlink_outcome_warns_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bogus (non-enum) outcome hits the defensive branch and warns its repr
    (kills the 'unexpected symlink outcome' warn + the return-False mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    monkeypatch.setattr(_accept, "create_relative_symlink", lambda *_a: "WEIRD")
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=_no_conflict,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "unexpected symlink outcome 'WEIRD'"]


def test_create_non_escape_adopt_error_warns_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-escape AdoptError from create surfaces via outcome.message
    (kills the outcome.message warn-arg + return-False mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root)

    def _raise_create(_r: Path, _s: str, _t: str) -> SymlinkOutcome:
        raise AdoptError("disk on fire", details={})

    monkeypatch.setattr(_accept, "create_relative_symlink", _raise_create)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=_no_conflict,
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "disk on fire"]


def test_backup_replace_backup_failure_warns_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When backup_real_file raises, _do_backup_replace warns the exc message + returns False."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")

    def _raise_backup(_r: Path, _t: str, *, timestamp: str) -> Path:
        raise AdoptError("backup blew up", details={})

    monkeypatch.setattr(_accept, "backup_real_file", _raise_backup)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "backup blew up"]


def test_backup_replace_success_journals_accepted(tmp_path: Path) -> None:
    """A successful backup_replace journals a symlink_accepted event
    (kills journal_path->None on the _do_backup_replace + _record call sites)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    journal = root / ".claude/state/journal.log"
    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
        journal_path=journal,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=None,
    )
    assert result is True
    assert len(mappings) == 1
    accepted = [e for e in _journal_entries(root) if e.kind == "symlink_accepted"]
    assert len(accepted) == 1


def test_backup_replace_create_fail_restore_success_warn_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create-fail-after-backup with a successful restore warns the exact 'restored' reason."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    real_create = _symlink.create_relative_symlink

    def _fail_after_backup(r: Path, src_rel: str, tgt_rel: str) -> SymlinkOutcome:
        candidate = r / tgt_rel
        if not candidate.exists() and not candidate.is_symlink():
            return SymlinkOutcome.SOURCE_MISSING
        return real_create(r, src_rel, tgt_rel)

    monkeypatch.setattr(_accept, "create_relative_symlink", _fail_after_backup)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "create after backup failed; original file restored"]


def test_backup_replace_create_and_restore_both_fail_preserved_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When create fails after backup AND restore_real_file also fails, the warn names the
    preserved backup path (kills the 'preserved at {backup_path}' warn mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root)
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("blocker\n", encoding="utf-8")
    real_create = _symlink.create_relative_symlink

    def _fail_after_backup(r: Path, src_rel: str, tgt_rel: str) -> SymlinkOutcome:
        candidate = r / tgt_rel
        if not candidate.exists() and not candidate.is_symlink():
            return SymlinkOutcome.SOURCE_MISSING
        return real_create(r, src_rel, tgt_rel)

    monkeypatch.setattr(_accept, "create_relative_symlink", _fail_after_backup)
    monkeypatch.setattr(_accept, "restore_real_file", lambda *_a, **_k: False)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="backup_replace"),
        warn=warns.append,
    )
    assert result is False
    assert len(warns) == 1
    assert warns[0].startswith(
        _SKIP_PREFIX + "create after backup failed; original file preserved at "
    )


def test_replace_remove_failure_warns_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When remove_symlink_at_target raises, _do_replace warns the exc message + returns False."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/old.md", "# Old\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/old.md", slot)

    def _raise_remove(_r: Path, _t: str) -> str:
        raise AdoptError("remove blew up", details={})

    monkeypatch.setattr(_accept, "remove_symlink_at_target", _raise_remove)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "remove blew up"]


def test_other_symlink_read_failure_warns_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When read_other_symlink_source_rel raises, accept warns the exc message + returns False."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/other.md", "# Other\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/other.md", slot)

    def _raise_read(_r: Path, _t: str) -> str:
        raise AdoptError("cannot read link", details={})

    monkeypatch.setattr(_accept, "read_other_symlink_source_rel", _raise_read)
    warns: list[str] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        [],
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=warns.append,
    )
    assert result is False
    assert warns == [_SKIP_PREFIX + "cannot read link"]


def test_replace_create_failure_restores_previous_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When create fails AFTER removing the old symlink, the previous link is restored
    verbatim and the exact warn fires (kills restore_symlink arg mutations, the
    removed_link None-check, and the failure-tail warn/return mutations)."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/old.md", "# Old\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    old_link = "../../legacy/old.md"
    os.symlink(old_link, slot)
    real_create = _symlink.create_relative_symlink

    def _fail_after_remove(r: Path, src_rel: str, tgt_rel: str) -> SymlinkOutcome:
        candidate = r / tgt_rel
        if not candidate.exists() and not candidate.is_symlink():
            return SymlinkOutcome.SOURCE_MISSING  # post-removal create "fails"
        return real_create(r, src_rel, tgt_rel)

    monkeypatch.setattr(_accept, "create_relative_symlink", _fail_after_remove)
    warns: list[str] = []
    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=warns.append,
    )
    assert result is False
    assert len(mappings) == 0
    assert slot.is_symlink()
    assert os.readlink(slot) == old_link
    assert warns == [
        _SKIP_PREFIX + "create after symlink-replace failed; previous symlink restored"
    ]


def test_replace_success_with_no_journal_does_not_crash(tmp_path: Path) -> None:
    """A successful replace with journal_path=None records the mapping without journaling
    (kills the `and`->`or` mutation on the replaced-event guard, which would call the
    journal writer with a None path)."""
    root = _scaffold(tmp_path)
    _write_source(root, _SOURCE_REL)
    _write_source(root, "legacy/old.md", "# Old\n")
    slot = root / _ARCH_TARGET
    slot.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../legacy/old.md", slot)
    mappings: list[SymlinkMapping] = []
    result = accept_one_artifact(
        root,
        _artifact(),
        _ARCH_TARGET,
        mappings,
        set(),
        journal_path=None,
        conflict=lambda *_: ConflictDecision(action="replace"),
        warn=None,
    )
    assert result is True
    assert len(mappings) == 1
    assert slot.is_symlink()

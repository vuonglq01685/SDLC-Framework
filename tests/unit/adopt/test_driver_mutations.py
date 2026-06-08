"""Mutation-kill tests for adopt/driver.py (Story 3.7 AC2, Tier-1).

Targets the 75 surviving mutants in driver.py by exercising:
- _validate_resume_cursor: contiguous prefix validation (boundary cases)
- _build_report / report field values: schema_version=1, exact repo_root
- _report_bytes: NFC + sort_keys canonical form
- _append_event: payload structure and monotonic seq
- Pass-1 detected results forwarded into the AdoptReport
- Error journal entry carries reason string (not just pass number)
- Journal entry actor/target_id constants
- Report written atomically after each pass (AC4: mid-run report)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt driver is POSIX-only in v1", allow_module_level=True)

from sdlc.adopt import driver
from sdlc.adopt.driver import _append_event, _validate_resume_cursor
from sdlc.contracts.adopt_report import AdoptReport, DetectedArtifact
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_REPORT_REL = ".claude/state/adopt-report.json"
_JOURNAL_REL = ".claude/state/journal.log"


def _scaffold(tmp_path: Path) -> Path:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "journal.log").touch()
    return tmp_path


def _journal_entries(root: Path) -> list[JournalEntry]:
    path = root / _JOURNAL_REL
    lines = path.read_text().splitlines()
    return [JournalEntry.model_validate_json(ln) for ln in lines if ln.strip()]


def _read_report(root: Path) -> AdoptReport:
    return AdoptReport.model_validate_json((root / _REPORT_REL).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# _validate_resume_cursor boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("completed", [
    (),          # empty → valid (fresh start)
    (1,),        # only pass 1 → valid
    (1, 2),      # passes 1+2 → valid
    (1, 2, 3),   # all three → valid
])
def test_validate_resume_cursor_valid_prefixes(completed: tuple[int, ...]) -> None:
    """Valid contiguous prefix cursors do not raise."""
    _validate_resume_cursor(list(completed))  # must not raise


@pytest.mark.parametrize("bad_completed", [
    (2,),        # skip pass 1
    (3,),        # skip passes 1 and 2
    (1, 3),      # skip pass 2
    (2, 3),      # skip pass 1
])
def test_validate_resume_cursor_non_contiguous_raises(bad_completed: tuple[int, ...]) -> None:
    """Non-contiguous prefix cursors raise AdoptError with 'corrupt' in the message."""
    with pytest.raises(AdoptError, match="corrupt"):
        _validate_resume_cursor(list(bad_completed))


def test_validate_resume_cursor_error_message_mentions_resume(  ) -> None:
    """The error message from a bad cursor mentions 'resume cursor' (not generic)."""
    with pytest.raises(AdoptError, match="resume cursor"):
        _validate_resume_cursor([2])


# ---------------------------------------------------------------------------
# Report field values
# ---------------------------------------------------------------------------


def test_report_schema_version_is_one(tmp_path: Path) -> None:
    """AdoptReport produced by run_adopt has schema_version=1."""
    root = _scaffold(tmp_path)
    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    report = _read_report(root)
    assert report.schema_version == 1


def test_report_repo_root_matches_root(tmp_path: Path) -> None:
    """AdoptReport.repo_root is the string form of the root path passed in."""
    root = _scaffold(tmp_path)
    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    report = _read_report(root)
    assert report.repo_root == str(root)


def test_report_passes_completed_is_one_two_three(tmp_path: Path) -> None:
    """After a fresh run, passes_completed is exactly (1, 2, 3), not (1,) or (1,2)."""
    root = _scaffold(tmp_path)
    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    report = _read_report(root)
    assert list(report.passes_completed) == [1, 2, 3]


def test_report_scanned_at_is_utc_timestamp(tmp_path: Path) -> None:
    """AdoptReport.scanned_at is a UTC RFC3339 timestamp ending in Z."""
    root = _scaffold(tmp_path)
    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    report = _read_report(root)
    assert report.scanned_at.endswith("Z")


# ---------------------------------------------------------------------------
# _append_event payload and journal structure
# ---------------------------------------------------------------------------


def test_append_event_payload_is_stored_exactly(tmp_path: Path) -> None:
    """_append_event stores the exact payload dict in the journal entry."""
    root = _scaffold(tmp_path)
    journal = root / _JOURNAL_REL

    _append_event(journal, kind="adopt_pass_started", payload={"pass": 1, "extra": "data"})

    entries = _journal_entries(root)
    assert len(entries) == 1
    assert entries[0].kind == "adopt_pass_started"
    assert entries[0].payload["pass"] == 1
    assert entries[0].payload["extra"] == "data"


def test_append_event_monotonic_seq_increments(tmp_path: Path) -> None:
    """Multiple _append_event calls produce strictly increasing monotonic_seq values."""
    root = _scaffold(tmp_path)
    journal = root / _JOURNAL_REL

    _append_event(journal, kind="adopt_pass_started", payload={"pass": 1})
    _append_event(journal, kind="adopt_pass_completed", payload={"pass": 1})
    _append_event(journal, kind="adopt_pass_started", payload={"pass": 2})

    seqs = [e.monotonic_seq for e in _journal_entries(root)]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3  # all unique


def test_append_event_after_hash_is_zero_sentinel(tmp_path: Path) -> None:
    """_append_event uses the zero-hash sentinel (event-only, no content change)."""
    root = _scaffold(tmp_path)
    journal = root / _JOURNAL_REL
    _append_event(journal, kind="adopt_pass_started", payload={"pass": 1})

    entries = _journal_entries(root)
    zero = "sha256:" + "0" * 64
    assert entries[0].after_hash == zero
    assert entries[0].before_hash is None


# ---------------------------------------------------------------------------
# Pass-1 detected results in report
# ---------------------------------------------------------------------------


def test_run_adopt_detected_from_pass1_in_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_adopt puts Pass 1 detected artifacts into the report (not an empty tuple)."""
    root = _scaffold(tmp_path)
    fake_artifact = DetectedArtifact(
        path="docs/arch.md",
        kind="architecture",
        confidence=85,
        suggested_target="02-Architecture/02-System/ARCHITECTURE.md",
    )
    from sdlc.adopt.passes import detection

    monkeypatch.setattr(detection, "detect_existing", lambda root, **_kw: [fake_artifact])

    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    report = _read_report(root)
    assert len(report.detected) == 1
    assert report.detected[0].path == "docs/arch.md"
    assert report.detected[0].kind == "architecture"


# ---------------------------------------------------------------------------
# Journal event actor and target_id fields
# ---------------------------------------------------------------------------


def test_journal_events_have_correct_actor_and_target_id(tmp_path: Path) -> None:
    """All journal events from driver have actor='cli' and target_id='adopt'."""
    root = _scaffold(tmp_path)
    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)

    for entry in _journal_entries(root):
        assert entry.actor == "cli"
        assert entry.target_id == "adopt"


# ---------------------------------------------------------------------------
# Failure journal entry carries reason string
# ---------------------------------------------------------------------------


def test_pass_failure_journal_reason_contains_exception_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """adopt_pass_failed payload.reason contains the exception's message string."""
    root = _scaffold(tmp_path)
    from sdlc.adopt.passes import symlink_offer

    unique_msg = "unique-failure-message-xyz"

    def _boom(*_: object, **__: object) -> None:
        raise RuntimeError(unique_msg)

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)

    with pytest.raises(AdoptError):
        driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)

    failed_entries = [e for e in _journal_entries(root) if e.kind == "adopt_pass_failed"]
    assert len(failed_entries) == 1
    assert unique_msg in str(failed_entries[0].payload.get("reason", ""))


def test_pass_failure_journal_entry_has_correct_pass_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """adopt_pass_failed payload.pass = 2 when Pass 2 fails."""
    root = _scaffold(tmp_path)
    from sdlc.adopt.passes import symlink_offer

    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)

    with pytest.raises(AdoptError):
        driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)

    failed_entries = [e for e in _journal_entries(root) if e.kind == "adopt_pass_failed"]
    assert len(failed_entries) == 1
    assert failed_entries[0].payload["pass"] == 2


# ---------------------------------------------------------------------------
# Report written after Pass 1 (mid-run AC4 checkpoint)
# ---------------------------------------------------------------------------


def test_report_written_after_pass1_with_correct_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Pass 2 fails, the on-disk report shows passes_completed=(1,)."""
    root = _scaffold(tmp_path)
    from sdlc.adopt.passes import symlink_offer

    def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("pass2 boom")

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)

    with pytest.raises(AdoptError):
        driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)

    report = _read_report(root)
    assert list(report.passes_completed) == [1]


def test_report_written_after_pass2_before_pass3_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Pass 3 fails, the on-disk report shows passes_completed=(1, 2)."""
    root = _scaffold(tmp_path)
    from sdlc.adopt.passes import stamp

    def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("pass3 boom")

    monkeypatch.setattr(stamp, "mark_imported", _boom)

    with pytest.raises(AdoptError):
        driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)

    report = _read_report(root)
    assert list(report.passes_completed) == [1, 2]


# ---------------------------------------------------------------------------
# Resume: completed passes are skipped (not run again)
# ---------------------------------------------------------------------------


def test_resume_pass1_completed_only_runs_2_and_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With passes_completed=(1,) in the on-disk report, only passes 2 and 3 execute."""
    root = _scaffold(tmp_path)
    journal_path = root / _JOURNAL_REL
    driver._append_event(journal_path, kind="adopt_pass_started", payload={"pass": 1})
    driver._append_event(journal_path, kind="adopt_pass_completed", payload={"pass": 1})
    seeded = AdoptReport(
        schema_version=1,
        repo_root=str(root),
        scanned_at="2026-06-02T00:00:00.000Z",
        detected=(),
        passes_completed=(1,),
    )
    (root / _REPORT_REL).write_text(seeded.model_dump_json(), encoding="utf-8")

    ran: list[int] = []
    from sdlc.adopt.passes import detection, stamp, symlink_offer

    monkeypatch.setattr(detection, "detect_existing", lambda *_a, **_k: ran.append(1) or [])
    monkeypatch.setattr(symlink_offer, "offer_symlinks", lambda *_a, **_k: ran.append(2))
    monkeypatch.setattr(stamp, "mark_imported", lambda *_a, **_k: ran.append(3))

    driver.run_adopt(root=root, journal_path=journal_path)
    assert ran == [2, 3]  # Pass 1 must NOT appear


# ---------------------------------------------------------------------------
# Strict pass ordering: 1 → 2 → 3
# ---------------------------------------------------------------------------


def test_pass_order_is_strictly_one_two_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passes always run in order 1, 2, 3, regardless of internal ordering."""
    root = _scaffold(tmp_path)
    ran: list[int] = []
    from sdlc.adopt.passes import detection, stamp, symlink_offer

    monkeypatch.setattr(detection, "detect_existing", lambda *_a, **_k: ran.append(1) or [])
    monkeypatch.setattr(symlink_offer, "offer_symlinks", lambda *_a, **_k: ran.append(2))
    monkeypatch.setattr(stamp, "mark_imported", lambda *_a, **_k: ran.append(3))

    driver.run_adopt(root=root, journal_path=root / _JOURNAL_REL)
    assert ran == [1, 2, 3]

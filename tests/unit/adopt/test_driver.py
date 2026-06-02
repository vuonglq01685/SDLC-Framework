"""Unit tests for the adopt three-pass orchestrator driver (Story 3.1, AC1/AC3/AC6).

Covers:
  * pass ordering (1 -> 2 -> 3, strict);
  * per-pass journaling (`adopt_pass_started` + `adopt_pass_completed`);
  * partial-failure resilience (`adopt_pass_failed` + report records last good pass);
  * pass-level resume (D3(a)) from `passes_completed`.

The driver is journal/state-only — the CLI layer (cli/adopt.py) owns scaffolding. These
tests give it a hand-built `.claude/state/` so the journal + report writes have a home.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover - journal writer is POSIX-only
    pytest.skip("adopt driver journals via POSIX-only writer", allow_module_level=True)

from sdlc.adopt import driver
from sdlc.contracts.adopt_report import AdoptReport
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit

_REPORT_REL = ".claude/state/adopt-report.json"
_JOURNAL_REL = ".claude/state/journal.log"


@pytest.fixture
def adopt_root(tmp_path: Path) -> Path:
    """A repo root with an empty, scaffolded `.claude/state/` (journal present)."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "journal.log").touch()
    return tmp_path


def _journal_kinds(root: Path) -> list[tuple[str, object]]:
    """Return [(kind, payload['pass']), ...] in on-disk order."""
    out: list[tuple[str, object]] = []
    journal_path = root / _JOURNAL_REL
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = JournalEntry.model_validate_json(line)
        out.append((entry.kind, entry.payload.get("pass")))
    return out


def _read_report(root: Path) -> AdoptReport:
    return AdoptReport.model_validate_json((root / _REPORT_REL).read_text(encoding="utf-8"))


# --- happy path -------------------------------------------------------------


def test_fresh_run_completes_all_three_passes(adopt_root: Path) -> None:
    report = driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    assert isinstance(report, AdoptReport)
    assert list(report.passes_completed) == [1, 2, 3]


def test_fresh_run_writes_report_with_empty_detected(adopt_root: Path) -> None:
    """3.1 detection seam returns [] — the detected shape is frozen, Pass 1 (3.2) fills it."""
    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    report = _read_report(adopt_root)
    assert report.detected == ()
    assert report.schema_version == 1
    assert report.repo_root == str(adopt_root)


def test_passes_run_in_strict_order(adopt_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    from sdlc.adopt.passes import detection, stamp, symlink_offer

    monkeypatch.setattr(detection, "detect_existing", lambda root: calls.append(1) or [])
    monkeypatch.setattr(symlink_offer, "offer_symlinks", lambda root, detected: calls.append(2))
    monkeypatch.setattr(stamp, "mark_imported", lambda root, detected: calls.append(3))

    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    assert calls == [1, 2, 3]


def test_each_pass_is_journaled_start_and_complete(adopt_root: Path) -> None:
    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    assert _journal_kinds(adopt_root) == [
        ("adopt_pass_started", 1),
        ("adopt_pass_completed", 1),
        ("adopt_pass_started", 2),
        ("adopt_pass_completed", 2),
        ("adopt_pass_started", 3),
        ("adopt_pass_completed", 3),
    ]


def test_pass_journal_entries_are_event_only_sentinel(adopt_root: Path) -> None:
    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    journal_path = adopt_root / _JOURNAL_REL
    zero = "sha256:" + "0" * 64
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        entry = JournalEntry.model_validate_json(line)
        assert entry.after_hash == zero
        assert entry.before_hash is None


# --- partial failure --------------------------------------------------------


def test_pass_failure_raises_adopt_error(adopt_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.adopt.passes import symlink_offer

    def _boom(root: Path, detected: object) -> None:
        raise RuntimeError("pass 2 exploded")

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)
    with pytest.raises(AdoptError):
        driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)


def test_pass_failure_records_last_good_pass(
    adopt_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.adopt.passes import symlink_offer

    def _boom(root: Path, detected: object) -> None:
        raise RuntimeError("pass 2 exploded")

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)
    with pytest.raises(AdoptError):
        driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)

    report = _read_report(adopt_root)
    assert list(report.passes_completed) == [1]


def test_pass_failure_is_journaled_with_pass_and_reason(
    adopt_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.adopt.passes import symlink_offer

    def _boom(root: Path, detected: object) -> None:
        raise RuntimeError("pass 2 exploded")

    monkeypatch.setattr(symlink_offer, "offer_symlinks", _boom)
    with pytest.raises(AdoptError):
        driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)

    kinds = _journal_kinds(adopt_root)
    assert ("adopt_pass_started", 2) in kinds
    assert ("adopt_pass_failed", 2) in kinds
    assert ("adopt_pass_completed", 2) not in kinds

    # the failure entry carries the reason
    journal_path = adopt_root / _JOURNAL_REL
    failed = [
        JournalEntry.model_validate_json(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if JournalEntry.model_validate_json(line).kind == "adopt_pass_failed"
    ]
    assert len(failed) == 1
    assert "exploded" in str(failed[0].payload["reason"])


# --- resume (D3(a) pass-level) ----------------------------------------------


def test_resume_skips_completed_passes(adopt_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # seed a prior report that completed pass 1
    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    # truncate journal + rewrite a report stuck at pass 1 to simulate a crash after pass 1
    (adopt_root / _JOURNAL_REL).write_text("", encoding="utf-8")
    seeded = AdoptReport(
        schema_version=1,
        repo_root=str(adopt_root),
        scanned_at="2026-06-02T00:00:00.000Z",
        detected=(),
        passes_completed=(1,),
    )
    (adopt_root / _REPORT_REL).write_text(seeded.model_dump_json(), encoding="utf-8")

    calls: list[int] = []
    from sdlc.adopt.passes import detection, stamp, symlink_offer

    monkeypatch.setattr(detection, "detect_existing", lambda root: calls.append(1) or [])
    monkeypatch.setattr(symlink_offer, "offer_symlinks", lambda root, detected: calls.append(2))
    monkeypatch.setattr(stamp, "mark_imported", lambda root, detected: calls.append(3))

    report = driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    # pass 1 was already complete → only 2 and 3 re-run
    assert calls == [2, 3]
    assert list(report.passes_completed) == [1, 2, 3]


def test_resume_journal_omits_completed_pass(
    adopt_root: Path,
) -> None:
    seeded = AdoptReport(
        schema_version=1,
        repo_root=str(adopt_root),
        scanned_at="2026-06-02T00:00:00.000Z",
        detected=(),
        passes_completed=(1,),
    )
    (adopt_root / _REPORT_REL).write_text(seeded.model_dump_json(), encoding="utf-8")

    driver.run_adopt(root=adopt_root, journal_path=adopt_root / _JOURNAL_REL)
    started_passes = [p for kind, p in _journal_kinds(adopt_root) if kind == "adopt_pass_started"]
    assert started_passes == [2, 3]

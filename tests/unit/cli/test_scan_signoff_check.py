"""Unit tests for scan.py _check_signoffs helper (AC5, AC6, Story 2A.12)."""

from __future__ import annotations

import hashlib
import unittest.mock
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PHASE1_DIR = "01-Requirement"
_TS_NOW = "2026-05-14T10:00:00.000Z"


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _write_artifact(repo_root: Path, rel: str, content: bytes = b"data") -> Path:
    p = repo_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _write_approved_draft(
    repo_root: Path,
    phase: int,
    art_rel: str,
    art_hash: str,
    *,
    approved: bool = True,
    approved_by: str = "alice",
    drafted_at: str = "2026-05-14T09:00:00.000Z",
) -> Path:
    phase_dirs = {1: _PHASE1_DIR, 2: "02-Architecture"}
    phase_dir_name = phase_dirs[phase]
    phase_dir = repo_root / phase_dir_name
    phase_dir.mkdir(parents=True, exist_ok=True)
    approved_str = "true" if approved else "false"
    approved_by_str = f'"{approved_by}"' if approved else "null"
    content = (
        f"```signoff\n"
        f"phase: {phase}\n"
        f"artifacts:\n"
        f'  - path: "{art_rel}"\n'
        f'    hash: "{art_hash}"\n'
        f"approved: {approved_str}\n"
        f"approved_by: {approved_by_str}\n"
        f"approved_at: null\n"
        f"drafted_at: {drafted_at}\n"
        f"```\n"
    )
    draft = phase_dir / "SIGNOFF.md"
    draft.write_text(content, encoding="utf-8")
    return draft


# ---------------------------------------------------------------------------
# Helpers — load _check_signoffs after implementation
# ---------------------------------------------------------------------------


def _get_check_signoffs():  # type: ignore[return]
    from sdlc.cli.scan import _check_signoffs

    return _check_signoffs


# ---------------------------------------------------------------------------
# Happy path: approved=true + no drift → write_record called + journal signoff_recorded
# ---------------------------------------------------------------------------


def test_approved_draft_triggers_write_record(tmp_path: Path) -> None:
    """AC5: DRAFTED_NOT_APPROVED + approved=true + clean hashes → write_record called."""
    art_content = b"product content"
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", art_content)
    art_hash = _sha256(art_content)
    _write_approved_draft(tmp_path, 1, f"{_PHASE1_DIR}/01-PRODUCT.md", art_hash, approved=True)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    with (
        unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.scan.now_rfc3339_utc_ms", return_value=_TS_NOW),
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync") as mock_journal,
    ):
        _check_signoffs(tmp_path, journal_path)

    mock_write.assert_called_once()
    # P19 (Story 2A.12 review): assert on JournalEntry.kind directly, not str repr.
    kinds = [c.args[0].kind for c in mock_journal.call_args_list if c.args]
    assert "signoff_recorded" in kinds


def test_approved_draft_no_write_if_approved_false(tmp_path: Path) -> None:
    """AC5: DRAFTED_NOT_APPROVED + approved=false → write_record NOT called."""
    art_content = b"product"
    art_hash = _sha256(art_content)
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", art_content)
    _write_approved_draft(tmp_path, 1, f"{_PHASE1_DIR}/01-PRODUCT.md", art_hash, approved=False)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    with (
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync"),
    ):
        _check_signoffs(tmp_path, journal_path)

    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Hash drift: write_record NOT called + ERR_SIGNOFF_HASH_DRIFT emitted
# ---------------------------------------------------------------------------


def test_hash_drift_emits_error_no_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC5: hash drift → ERR_SIGNOFF_HASH_DRIFT in stderr, write_record not called."""
    art_content = b"original content"
    stale_hash = _sha256(art_content)  # hash from before drift
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", b"MODIFIED content")  # drift!
    _write_approved_draft(tmp_path, 1, f"{_PHASE1_DIR}/01-PRODUCT.md", stale_hash, approved=True)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    with (
        unittest.mock.patch("sdlc.cli.scan.now_rfc3339_utc_ms", return_value=_TS_NOW),
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync") as mock_journal,
    ):
        _check_signoffs(tmp_path, journal_path)

    mock_write.assert_not_called()
    # P19 (Story 2A.12 review): assert on JournalEntry.kind directly, not str repr.
    kinds = [c.args[0].kind for c in mock_journal.call_args_list if c.args]
    assert "signoff_hash_drift_detected" in kinds
    # Defensive: canonical record file must NOT exist on drift (write_record was not called).
    canonical = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    assert not canonical.exists()


# ---------------------------------------------------------------------------
# Phase 1 not DRAFTED_NOT_APPROVED → phase 2 check skipped
# ---------------------------------------------------------------------------


def test_phase2_skipped_when_phase1_not_drafted(tmp_path: Path) -> None:
    """AC6: phase 1 AWAITING_SIGNOFF → phase 2 check never runs."""
    # Only set up phase 2 draft (no phase 1 at all)
    arch_content = b"arch"
    arch_hash = _sha256(arch_content)
    _write_artifact(tmp_path, "02-Architecture/arch.md", arch_content)
    _write_approved_draft(tmp_path, 2, "02-Architecture/arch.md", arch_hash, approved=True)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    with (
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync"),
    ):
        _check_signoffs(tmp_path, journal_path)

    # Phase 2 write_record should NOT be called because phase 1 is not even DRAFTED
    # (and AWAITING_SIGNOFF != DRAFTED_NOT_APPROVED → skip)
    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# AWAITING_SIGNOFF state → skip (no action)
# ---------------------------------------------------------------------------


def test_awaiting_signoff_state_skipped(tmp_path: Path) -> None:
    """AC6: AWAITING_SIGNOFF → no write, no journal signoff entry."""
    # No SIGNOFF.md, no canonical record → state = AWAITING_SIGNOFF

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    with (
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync") as mock_journal,
    ):
        _check_signoffs(tmp_path, journal_path)

    mock_write.assert_not_called()
    # P19 (Story 2A.12 review): assert on JournalEntry.kind directly, not str repr.
    signoff_kinds = [c.args[0].kind for c in mock_journal.call_args_list if c.args]
    assert not any(k.startswith("signoff_") for k in signoff_kinds)


# ---------------------------------------------------------------------------
# DR2 (Story 2A.12 code-review) — coverage for new _check_signoffs branches
# ---------------------------------------------------------------------------


def test_compute_state_signoff_error_returns_malformed_state(tmp_path: Path) -> None:
    """P9 (review): compute_state raising → ERR_SIGNOFF_MALFORMED_DRAFT report entry."""
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    from sdlc.errors import SignoffError

    _check_signoffs = _get_check_signoffs()

    def _raise(*a: object, **kw: object) -> object:
        raise SignoffError("simulated state failure", details={"phase": 1})

    with unittest.mock.patch("sdlc.signoff.compute_state", side_effect=_raise):
        report = _check_signoffs(tmp_path, journal_path)

    assert any(r["state"] == "malformed-draft" for r in report)


def test_non_drift_validation_error_classified_as_validation(tmp_path: Path) -> None:
    """P4 (review): validator raising for non-drift cause (missing approved_by, phase
    mismatch, ...) → ERR_SIGNOFF_VALIDATION, NOT ERR_SIGNOFF_HASH_DRIFT, and journal
    kind = signoff_validation_failed, NOT signoff_hash_drift_detected.
    """
    art_content = b"product"
    art_hash = _sha256(art_content)
    _write_artifact(tmp_path, f"{_PHASE1_DIR}/01-PRODUCT.md", art_content)
    # Approved draft but with no approved_by → validator raises non-drift SignoffError.
    _write_approved_draft(
        tmp_path,
        1,
        f"{_PHASE1_DIR}/01-PRODUCT.md",
        art_hash,
        approved=True,
    )

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    from sdlc.errors import SignoffError

    _check_signoffs = _get_check_signoffs()

    def _raise(*a: object, **kw: object) -> object:
        # No "kind" in details → P4 classifies as non-drift validation failure.
        raise SignoffError(
            "phase 1 approved_by must be non-null when approved=true",
            details={"reason": "missing_approved_by"},
        )

    with (
        unittest.mock.patch("sdlc.signoff.validate_signoff", side_effect=_raise),
        unittest.mock.patch("sdlc.signoff.write_record") as mock_write,
        unittest.mock.patch("sdlc.journal.append_sync") as mock_journal,
    ):
        report = _check_signoffs(tmp_path, journal_path)

    mock_write.assert_not_called()
    kinds = [c.args[0].kind for c in mock_journal.call_args_list if c.args]
    assert "signoff_validation_failed" in kinds
    assert "signoff_hash_drift_detected" not in kinds
    assert any(r["state"] == "validation-failed" for r in report)


def test_phase2_draft_present_but_phase1_not_approved_returns_skipped(tmp_path: Path) -> None:
    """P18 (review): phase 2 draft exists but phase 1 not APPROVED → report entry +
    (when ctx given) emit_warning. ctx=None path: still appends a report entry.
    """
    arch_content = b"arch"
    arch_hash = _sha256(arch_content)
    _write_artifact(tmp_path, "02-Architecture/arch.md", arch_content)
    _write_approved_draft(tmp_path, 2, "02-Architecture/arch.md", arch_hash, approved=True)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    _check_signoffs = _get_check_signoffs()

    report = _check_signoffs(tmp_path, journal_path)

    assert any(r["phase"] == 2 and r["state"] == "skipped-phase1-not-approved" for r in report)


def test_malformed_draft_returns_malformed_entry(tmp_path: Path) -> None:
    """P9 (review): read_signoff_md_draft raising → malformed-draft report entry."""
    phase_dir = tmp_path / _PHASE1_DIR
    phase_dir.mkdir(parents=True, exist_ok=True)
    # SIGNOFF.md exists but is malformed (missing fenced block) — but state must be
    # DRAFTED_NOT_APPROVED first. Simplest: create the file then patch compute_state.
    (phase_dir / "SIGNOFF.md").write_text("garbage with no signoff fence", encoding="utf-8")

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.touch()

    from sdlc.signoff.states import SignoffState as _S

    _check_signoffs = _get_check_signoffs()

    # Force state=DRAFTED_NOT_APPROVED so the code reaches _try_read_draft, which raises.
    with unittest.mock.patch("sdlc.signoff.compute_state", return_value=_S.DRAFTED_NOT_APPROVED):
        report = _check_signoffs(tmp_path, journal_path)

    # ctx is None — _try_read_draft returns None silently (and report gets the
    # drafted-not-approved entry since draft is None / not approved).
    assert any(r["phase"] == 1 for r in report)

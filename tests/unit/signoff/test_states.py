"""Unit tests for signoff/states.py — SignoffState + compute_state (AC1, AC10, Story 2A.7)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS3 = "2026-05-10T12:01:00.000Z"

_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}


def _write_draft(
    repo_root: Path,
    phase: int,
    *,
    approved: bool = False,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> Path:
    """Create a SIGNOFF.md draft in the phase dir."""
    phase_dir = repo_root / _PHASE_DIR[phase]
    phase_dir.mkdir(parents=True, exist_ok=True)
    draft_path = phase_dir / "SIGNOFF.md"
    approved_by_val = f'"{approved_by}"' if approved_by else "null"
    approved_at_val = f'"{approved_at}"' if approved_at else "null"
    draft_path.write_text(
        textwrap.dedent(f"""\
            ---
            schema_version: 1
            phase: {phase}
            artifacts:
              - path: "{_PHASE_DIR[phase]}/PRODUCT.md"
                hash: "{_VALID_HASH}"
            approved: {str(approved).lower()}
            approved_by: {approved_by_val}
            approved_at: {approved_at_val}
            drafted_at: "{_TS1}"
            ---
        """),
        encoding="utf-8",
    )
    return draft_path


def _write_canonical(
    repo_root: Path,
    phase: int,
    *,
    invalidated_at: str | None = None,
) -> Path:
    """Create a canonical signoff record for phase."""
    from sdlc.signoff.records import ArtifactRef, SignoffRecord, write_record

    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[phase]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS3,
        invalidated_at=invalidated_at,
    )
    # write_record refuses overwrite; use _write_bytes_to_disk directly for invalidated records
    if invalidated_at is not None:
        from sdlc.signoff.records import _canonicalize_record, _signoff_path, _write_bytes_to_disk

        target = _signoff_path(phase, repo_root)
        _write_bytes_to_disk(target, _canonicalize_record(record))
    else:
        write_record(record, repo_root=repo_root)
    return repo_root / ".claude" / "state" / "signoffs" / f"phase-{phase}.yaml"


# ---------------------------------------------------------------------------
# SignoffState enum
# ---------------------------------------------------------------------------


def test_signoff_state_enum_values() -> None:
    from sdlc.signoff.states import SignoffState

    assert SignoffState.AWAITING_SIGNOFF.value == "awaiting-signoff"
    assert SignoffState.DRAFTED_NOT_APPROVED.value == "drafted-not-approved"
    assert SignoffState.APPROVED.value == "approved"
    assert SignoffState.INVALIDATED_BY_REPLAN.value == "invalidated-by-replan"


def test_signoff_state_is_str() -> None:
    from sdlc.signoff.states import SignoffState

    assert isinstance(SignoffState.APPROVED, str)


# ---------------------------------------------------------------------------
# compute_state — phase 1 matrix
# ---------------------------------------------------------------------------


def test_compute_state_awaiting_signoff_no_draft_no_record(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.AWAITING_SIGNOFF


def test_compute_state_drafted_not_approved_when_draft_false(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_draft(tmp_path, phase=1, approved=False)
    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.DRAFTED_NOT_APPROVED


def test_compute_state_drafted_not_approved_even_when_draft_says_true(tmp_path: Path) -> None:
    """Draft approved=true without canonical record → still DRAFTED_NOT_APPROVED."""
    from sdlc.signoff.states import SignoffState, compute_state

    _write_draft(tmp_path, phase=1, approved=True, approved_by="alice", approved_at=_TS2)
    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.DRAFTED_NOT_APPROVED


def test_compute_state_approved_when_canonical_exists(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_draft(tmp_path, phase=1, approved=True, approved_by="alice", approved_at=_TS2)
    _write_canonical(tmp_path, phase=1)
    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.APPROVED


def test_compute_state_approved_without_draft(tmp_path: Path) -> None:
    """Canonical record exists; no draft needed — still APPROVED."""
    from sdlc.signoff.states import SignoffState, compute_state

    _write_canonical(tmp_path, phase=1)
    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.APPROVED


def test_compute_state_invalidated_by_replan(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_canonical(tmp_path, phase=1, invalidated_at=_TS3)
    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.INVALIDATED_BY_REPLAN


# ---------------------------------------------------------------------------
# compute_state — phase 2 same matrix
# ---------------------------------------------------------------------------


def test_compute_state_phase2_awaiting(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.AWAITING_SIGNOFF


def test_compute_state_phase2_drafted(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_draft(tmp_path, phase=2, approved=False)
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.DRAFTED_NOT_APPROVED


def test_compute_state_phase2_approved(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_canonical(tmp_path, phase=2)
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.APPROVED


def test_compute_state_phase2_invalidated(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    _write_canonical(tmp_path, phase=2, invalidated_at=_TS3)
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN


# ---------------------------------------------------------------------------
# compute_state — phase 3 AC10
# ---------------------------------------------------------------------------


def test_compute_state_phase3_strict_false_returns_awaiting(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    result = compute_state(phase=3, repo_root=tmp_path, strict=False)
    assert result == SignoffState.AWAITING_SIGNOFF


def test_compute_state_phase3_default_is_strict_false(tmp_path: Path) -> None:
    from sdlc.signoff.states import SignoffState, compute_state

    # Default call (no strict kwarg) should return AWAITING_SIGNOFF for phase 3
    result = compute_state(phase=3, repo_root=tmp_path)
    assert result == SignoffState.AWAITING_SIGNOFF


def test_compute_state_phase3_strict_true_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.states import compute_state

    with pytest.raises(SignoffError, match="phase 3"):
        compute_state(phase=3, repo_root=tmp_path, strict=True)


def test_compute_state_phase3_warn_logged_once(tmp_path: Path) -> None:
    """After first call, _phase3_warned is True; both calls return AWAITING_SIGNOFF."""
    import sdlc.signoff.states as states_mod
    from sdlc.signoff.states import SignoffState, compute_state

    states_mod._phase3_warned = False  # reset for repeatability

    r1 = compute_state(phase=3, repo_root=tmp_path)
    assert states_mod._phase3_warned is True
    r2 = compute_state(phase=3, repo_root=tmp_path)
    assert r1 == SignoffState.AWAITING_SIGNOFF
    assert r2 == SignoffState.AWAITING_SIGNOFF


# ---------------------------------------------------------------------------
# compute_state — out-of-range phases
# ---------------------------------------------------------------------------


def test_compute_state_phase_zero_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.states import compute_state

    with pytest.raises(SignoffError, match="phase out of range"):
        compute_state(phase=0, repo_root=tmp_path)


def test_compute_state_phase_four_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.states import compute_state

    with pytest.raises(SignoffError, match="phase out of range"):
        compute_state(phase=4, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# compute_state — malformed canonical record raises
# ---------------------------------------------------------------------------


def test_compute_state_malformed_canonical_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.states import compute_state

    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True)
    (signoff_dir / "phase-1.yaml").write_text("}{bad yaml}{", encoding="utf-8")

    with pytest.raises(SignoffError):
        compute_state(phase=1, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# compute_state — malformed SIGNOFF.md draft is tolerated (returns AWAITING)
# ---------------------------------------------------------------------------


def test_compute_state_malformed_draft_falls_back_to_awaiting(tmp_path: Path) -> None:
    """A corrupt SIGNOFF.md draft should fall back to AWAITING_SIGNOFF gracefully."""
    from sdlc.signoff.states import SignoffState, compute_state

    draft_dir = tmp_path / "01-Requirement"
    draft_dir.mkdir(parents=True)
    (draft_dir / "SIGNOFF.md").write_text("not yaml at all }{", encoding="utf-8")

    result = compute_state(phase=1, repo_root=tmp_path)
    assert result == SignoffState.AWAITING_SIGNOFF

"""Integration tests: signoff invalidation + replan behavior (AC6, Story 2A.7 Task 7.3).

Covers:
  - write_record → invalidate_record → write_record AGAIN refuses (file still exists)
  - invalidate_record round-trip preserves all fields except invalidated_at/reason
  - compute_state returns INVALIDATED_BY_REPLAN after invalidation
  - phase_gate denies phase-N+1 writes after phase-N invalidation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import SignoffError
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.signoff import (
    ArtifactRef,
    SignoffRecord,
    SignoffState,
    compute_state,
    invalidate_record,
    read_record,
    write_record,
)
from sdlc.signoff.hasher import compute_artifact_hash

_TS1 = "2026-05-10T09:00:00.000Z"
_TS2 = "2026-05-10T10:00:00.000Z"
_TS3 = "2026-05-10T11:00:00.000Z"
_TS_INVAL = "2026-05-10T12:00:00.000Z"

_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}


def _write_approved_record(tmp_path: Path, phase: int) -> SignoffRecord:
    """Write a canonical SignoffRecord for phase with one placeholder artifact."""
    phase_dir_name = _PHASE_DIR[phase]
    phase_dir = tmp_path / phase_dir_name
    phase_dir.mkdir(parents=True, exist_ok=True)
    artifact = phase_dir / "PLACEHOLDER.md"
    artifact.write_bytes(b"placeholder for replan test")

    artifact_hash = compute_artifact_hash(artifact, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{phase_dir_name}/PLACEHOLDER.md", hash=artifact_hash),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)
    return record


@pytest.mark.integration
class TestSignoffReplanInvalidation:
    def test_write_then_invalidate_then_write_again_succeeds(self, tmp_path: Path) -> None:
        """Replan flow (D4): write_record → invalidate_record → write_record SUCCEEDS.

        AC5/D4 — once a record is invalidated, the post-replan re-approval flow
        is allowed to overwrite it without an explicit unblock step. write_record
        still refuses to clobber a non-invalidated APPROVED record.
        """
        _write_approved_record(tmp_path, phase=1)
        invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_TS_INVAL)

        phase_dir_name = _PHASE_DIR[1]
        phase_dir = tmp_path / phase_dir_name
        artifact = phase_dir / "PLACEHOLDER_V2.md"
        artifact.write_bytes(b"new content after replan")
        new_hash = compute_artifact_hash(artifact, repo_root=tmp_path)

        new_record = SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path=f"{phase_dir_name}/PLACEHOLDER_V2.md", hash=new_hash),),
            approved_by="bob",
            approved_at=_TS3,
            drafted_at=_TS2,
            validated_at=_TS3,
        )
        # Invalidated records are overwritable per D4 — re-approval flow lands cleanly.
        write_record(new_record, repo_root=tmp_path)
        from sdlc.signoff.records import read_record

        roundtrip = read_record(1, repo_root=tmp_path)
        assert roundtrip is not None
        assert roundtrip.invalidated_at is None
        assert roundtrip.approved_by == "bob"

        # Conversely, after the new APPROVED record is in place, write_record refuses
        # to clobber it (the original guard remains in force for live signoffs).
        with pytest.raises(SignoffError, match="cannot overwrite"):
            write_record(new_record, repo_root=tmp_path)

    def test_invalidate_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        """invalidate_record preserves original fields; only adds invalidated_at/reason."""
        original = _write_approved_record(tmp_path, phase=1)
        updated = invalidate_record(
            1,
            repo_root=tmp_path,
            reason="sprint replan v2",
            now_utc=_TS_INVAL,
        )

        assert updated.phase == original.phase
        assert updated.artifacts == original.artifacts
        assert updated.approved_by == original.approved_by
        assert updated.approved_at == original.approved_at
        assert updated.drafted_at == original.drafted_at
        assert updated.validated_at == original.validated_at
        assert updated.invalidated_at == _TS_INVAL
        assert updated.invalidated_reason == "sprint replan v2"

    def test_compute_state_returns_invalidated_by_replan(self, tmp_path: Path) -> None:
        """compute_state returns INVALIDATED_BY_REPLAN after invalidation."""
        _write_approved_record(tmp_path, phase=1)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED

        invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_TS_INVAL)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

    def test_phase_gate_denies_phase2_after_phase1_invalidated(self, tmp_path: Path) -> None:
        """phase_gate denies phase-2 writes when phase-1 is INVALIDATED_BY_REPLAN."""
        from sdlc.contracts.hook_payload import HookPayload

        _write_approved_record(tmp_path, phase=1)
        invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_TS_INVAL)

        payload = HookPayload(
            hook_name="phase_gate",
            target_path="02-Architecture/01-UX/01-tokens.md",
            target_kind="write_intent",
            content_hash_before=None,
            write_intent="update architecture",
        )
        result = phase_gate(
            payload,
            repo_root=tmp_path,
            signoff_reader=lambda ph, rr: compute_state(ph, repo_root=rr),
        )
        assert result.decision == "deny"
        assert "invalidated by replan" in (result.reason or "")

    def test_phase_gate_denies_phase3_after_phase2_invalidated(self, tmp_path: Path) -> None:
        """phase_gate denies phase-3 writes when phase-2 is INVALIDATED_BY_REPLAN."""
        from sdlc.contracts.hook_payload import HookPayload

        _write_approved_record(tmp_path, phase=2)
        invalidate_record(2, repo_root=tmp_path, reason="arch replan", now_utc=_TS_INVAL)

        payload = HookPayload(
            hook_name="phase_gate",
            target_path="03-Implementation/01-API/server.py",
            target_kind="write_intent",
            content_hash_before=None,
            write_intent="create server",
        )
        result = phase_gate(
            payload,
            repo_root=tmp_path,
            signoff_reader=lambda ph, rr: compute_state(ph, repo_root=rr),
        )
        assert result.decision == "deny"
        assert "invalidated by replan" in (result.reason or "")

    def test_invalidate_nonexistent_raises(self, tmp_path: Path) -> None:
        """invalidate_record on a phase with no record raises SignoffError."""
        with pytest.raises(SignoffError, match="no canonical record found"):
            invalidate_record(1, repo_root=tmp_path, reason="no record", now_utc=_TS_INVAL)

    def test_persisted_invalidated_record_readable(self, tmp_path: Path) -> None:
        """read_record after invalidation returns the updated record with invalidated fields."""
        _write_approved_record(tmp_path, phase=1)
        invalidate_record(1, repo_root=tmp_path, reason="schema change", now_utc=_TS_INVAL)

        rec = read_record(phase=1, repo_root=tmp_path)
        assert rec is not None
        assert rec.invalidated_at == _TS_INVAL
        assert rec.invalidated_reason == "schema change"

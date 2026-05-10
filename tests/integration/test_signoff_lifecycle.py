"""Integration tests: full signoff lifecycle (AC3, AC5, AC6, Story 2A.7 Task 7.1).

Exercises the complete draft → approve → validate → write_record → compute_state
→ invalidate_record lifecycle on a real tmp_path repo.

Test matrix:
  - Phase 1 happy path: 3 artifacts, full lifecycle, state == APPROVED
  - Phase 1 drift path: artifact mutated after draft → validate raises
  - Phase 1 invalidation: write record → invalidate → state == INVALIDATED_BY_REPLAN
  - Phase 2 happy path: phase 1 already approved; phase 2 lifecycle succeeds
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import SignoffError
from sdlc.signoff import (
    ArtifactRef,
    SignoffRecord,
    SignoffState,
    compute_state,
    invalidate_record,
    read_record,
    validate_signoff,
    write_record,
)
from sdlc.signoff.hasher import compute_artifact_hash

_TS1 = "2026-05-10T10:00:00.000Z"
_TS2 = "2026-05-10T11:00:00.000Z"
_TS3 = "2026-05-10T12:00:00.000Z"

_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_artifact(repo_root: Path, phase: int, name: str, content: bytes) -> Path:
    phase_dir = repo_root / _PHASE_DIR[phase]
    phase_dir.mkdir(parents=True, exist_ok=True)
    p = phase_dir / name
    p.write_bytes(content)
    return p


def _write_signoff_draft(
    repo_root: Path,
    phase: int,
    artifacts: list[tuple[str, str]],
    *,
    approved: bool,
) -> Path:
    phase_dir_name = _PHASE_DIR[phase]
    phase_dir = repo_root / phase_dir_name
    phase_dir.mkdir(parents=True, exist_ok=True)

    art_lines = ""
    for rel_path, h in artifacts:
        art_lines += f'  - path: "{rel_path}"\n'
        art_lines += f'    hash: "{h}"\n'

    approved_by_val = '"alice"' if approved else "null"
    approved_at_val = f'"{_TS2}"' if approved else "null"

    draft = phase_dir / "SIGNOFF.md"
    draft.write_text(
        f"---\n"
        f"schema_version: 1\n"
        f"phase: {phase}\n"
        f"artifacts:\n"
        f"{art_lines}"
        f"approved: {str(approved).lower()}\n"
        f"approved_by: {approved_by_val}\n"
        f"approved_at: {approved_at_val}\n"
        f'drafted_at: "{_TS1}"\n'
        f"---\n",
        encoding="utf-8",
    )
    return draft


def _full_approve(repo_root: Path, phase: int, artifacts_bytes: dict[str, bytes]) -> SignoffRecord:
    """Create artifact files, draft + approve, validate, write record. Returns record."""
    phase_dir_name = _PHASE_DIR[phase]
    hashes: dict[str, str] = {}
    for name, content in artifacts_bytes.items():
        artifact = _create_artifact(repo_root, phase, name, content)
        rel = f"{phase_dir_name}/{name}"
        hashes[rel] = compute_artifact_hash(artifact, repo_root=repo_root)

    _write_signoff_draft(repo_root, phase, list(hashes.items()), approved=True)
    result = validate_signoff(phase=phase, repo_root=repo_root, now_utc=_TS3)
    write_record(result.record, repo_root=repo_root)
    return result.record


# ---------------------------------------------------------------------------
# Phase 1 happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSignoffLifecyclePhase1:
    def test_phase1_happy_path_three_artifacts(self, tmp_path: Path) -> None:
        """Full phase-1 lifecycle with 3 artifacts ends at APPROVED."""
        record = _full_approve(
            tmp_path,
            phase=1,
            artifacts_bytes={
                "PRODUCT.md": b"product content",
                "ASSUMPTIONS.md": b"assumption content",
                "GLOSSARY.md": b"glossary content",
            },
        )
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED
        assert len(record.artifacts) == 3

        persisted = read_record(phase=1, repo_root=tmp_path)
        assert persisted is not None
        assert persisted.phase == 1
        assert persisted.invalidated_at is None

    def test_phase1_validate_returns_approved_state(self, tmp_path: Path) -> None:
        """validate_signoff returns ValidatedSignoff.state == APPROVED before write_record."""
        phase_dir_name = _PHASE_DIR[1]
        artifact = _create_artifact(tmp_path, 1, "PRODUCT.md", b"content")
        rel = f"{phase_dir_name}/PRODUCT.md"
        h = compute_artifact_hash(artifact, repo_root=tmp_path)

        _write_signoff_draft(tmp_path, 1, [(rel, h)], approved=True)

        result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS3)
        assert result.state == SignoffState.APPROVED
        assert result.drift == ()
        assert result.record.phase == 1
        # State is still DRAFTED_NOT_APPROVED until write_record is called
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.DRAFTED_NOT_APPROVED

    def test_phase1_drift_raises_on_artifact_mutation(self, tmp_path: Path) -> None:
        """Artifact mutated after draft → validate_signoff raises hash-drift SignoffError."""
        phase_dir_name = _PHASE_DIR[1]
        artifact = _create_artifact(tmp_path, 1, "PRODUCT.md", b"original content")
        rel = f"{phase_dir_name}/PRODUCT.md"
        h = compute_artifact_hash(artifact, repo_root=tmp_path)

        _write_signoff_draft(tmp_path, 1, [(rel, h)], approved=True)

        # Mutate the artifact after drafting the signoff
        artifact.write_bytes(b"tampered content")

        with pytest.raises(SignoffError) as exc_info:
            validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS3)

        assert exc_info.value.details["kind"] == "drifted"
        assert "PRODUCT.md" in exc_info.value.details["artifact_path"]

    def test_phase1_missing_artifact_raises(self, tmp_path: Path) -> None:
        """Artifact deleted after draft → validate_signoff raises kind=missing."""
        phase_dir_name = _PHASE_DIR[1]
        artifact = _create_artifact(tmp_path, 1, "PRODUCT.md", b"content")
        rel = f"{phase_dir_name}/PRODUCT.md"
        h = compute_artifact_hash(artifact, repo_root=tmp_path)

        _write_signoff_draft(tmp_path, 1, [(rel, h)], approved=True)

        # Delete artifact after drafting
        artifact.unlink()

        with pytest.raises(SignoffError) as exc_info:
            validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS3)

        assert exc_info.value.details["kind"] == "missing"

    def test_phase1_invalidation_changes_state(self, tmp_path: Path) -> None:
        """write_record → APPROVED; invalidate_record → INVALIDATED_BY_REPLAN."""
        _full_approve(tmp_path, phase=1, artifacts_bytes={"PRODUCT.md": b"content"})
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED

        invalidate_record(
            1,
            repo_root=tmp_path,
            reason="requirements changed during sprint",
            now_utc=_TS3,
        )
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

        rec = read_record(phase=1, repo_root=tmp_path)
        assert rec is not None
        assert rec.invalidated_at == _TS3
        assert rec.invalidated_reason == "requirements changed during sprint"

    def test_phase1_state_progression_full(self, tmp_path: Path) -> None:
        """State machine progression: AWAITING → DRAFTED → APPROVED → INVALIDATED."""
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.AWAITING_SIGNOFF

        phase_dir_name = _PHASE_DIR[1]
        artifact = _create_artifact(tmp_path, 1, "PRODUCT.md", b"content")
        rel = f"{phase_dir_name}/PRODUCT.md"
        h = compute_artifact_hash(artifact, repo_root=tmp_path)
        _write_signoff_draft(tmp_path, 1, [(rel, h)], approved=False)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.DRAFTED_NOT_APPROVED

        _write_signoff_draft(tmp_path, 1, [(rel, h)], approved=True)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.DRAFTED_NOT_APPROVED

        result = validate_signoff(phase=1, repo_root=tmp_path, now_utc=_TS3)
        write_record(result.record, repo_root=tmp_path)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED

        invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_TS3)
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN


# ---------------------------------------------------------------------------
# Phase 2 happy path (requires phase 1 approved)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSignoffLifecyclePhase2:
    def test_phase2_happy_path_after_phase1_approved(self, tmp_path: Path) -> None:
        """Phase 2 lifecycle succeeds only after phase 1 is APPROVED."""
        _full_approve(tmp_path, phase=1, artifacts_bytes={"PRODUCT.md": b"p1 content"})
        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED

        _full_approve(tmp_path, phase=2, artifacts_bytes={"ARCHITECTURE.md": b"p2 content"})
        assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.APPROVED

    def test_phase2_both_records_coexist(self, tmp_path: Path) -> None:
        """Phase 1 and Phase 2 records can coexist independently."""
        _full_approve(tmp_path, phase=1, artifacts_bytes={"PRODUCT.md": b"p1"})
        _full_approve(tmp_path, phase=2, artifacts_bytes={"ARCHITECTURE.md": b"p2"})

        r1 = read_record(phase=1, repo_root=tmp_path)
        r2 = read_record(phase=2, repo_root=tmp_path)
        assert r1 is not None and r1.phase == 1
        assert r2 is not None and r2.phase == 2

    def test_phase2_invalidation_does_not_affect_phase1(self, tmp_path: Path) -> None:
        """Invalidating phase 2 does not change phase 1 state."""
        _full_approve(tmp_path, phase=1, artifacts_bytes={"PRODUCT.md": b"p1"})
        _full_approve(tmp_path, phase=2, artifacts_bytes={"ARCHITECTURE.md": b"p2"})

        invalidate_record(2, repo_root=tmp_path, reason="arch replan", now_utc=_TS3)

        assert compute_state(phase=1, repo_root=tmp_path) == SignoffState.APPROVED
        assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

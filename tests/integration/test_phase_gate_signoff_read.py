"""Integration tests for phase_gate DI signoff reader (AC5, AC7, Story 2A.4 + 2A.7).

Verifies that phase_gate correctly gates Phase-2 and Phase-3 paths when wired
to compute_state via the signoff_reader DI parameter (D2 decision, AC11).

State coverage:
  APPROVED               → allow
  AWAITING_SIGNOFF       → deny ("not found")
  DRAFTED_NOT_APPROVED   → deny ("drafted but not yet approved")
  INVALIDATED_BY_REPLAN  → deny ("invalidated by replan")
  reader exception       → deny ("reader raised") — fail-safe posture
"""

from __future__ import annotations

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.signoff import (
    ArtifactRef,
    SignoffRecord,
    compute_state,
    invalidate_record,
    write_record,
)
from sdlc.signoff.hasher import compute_artifact_hash

_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS3 = "2026-05-10T13:00:00.000Z"

_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}


def _p(path: str) -> HookPayload:
    return HookPayload(
        hook_name="phase_gate",
        target_path=path,
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="test write",
    )


def _reader(repo_root):
    return lambda ph, rr: compute_state(ph, repo_root=rr)


def _write_approved_record(tmp_path, phase: int) -> None:
    """Create a minimal approved canonical record using write_record."""
    phase_dir_name = _PHASE_DIR[phase]
    phase_dir = tmp_path / phase_dir_name
    phase_dir.mkdir(parents=True, exist_ok=True)
    artifact = phase_dir / "PLACEHOLDER.md"
    artifact.write_bytes(b"placeholder content for phase gate testing")

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


def _write_draft(tmp_path, phase: int, *, approved: bool = False) -> None:
    """Write a SIGNOFF.md draft with real hash for the DRAFTED_NOT_APPROVED case."""
    phase_dir_name = _PHASE_DIR[phase]
    phase_dir = tmp_path / phase_dir_name
    phase_dir.mkdir(parents=True, exist_ok=True)
    artifact = phase_dir / "PLACEHOLDER.md"
    artifact.write_bytes(b"placeholder for draft test")

    artifact_hash = compute_artifact_hash(artifact, repo_root=tmp_path)
    approved_by_val = '"alice"' if approved else "null"
    approved_at_val = f'"{_TS2}"' if approved else "null"

    draft = phase_dir / "SIGNOFF.md"
    draft.write_text(
        f"---\n"
        f"schema_version: 1\n"
        f"phase: {phase}\n"
        f"artifacts:\n"
        f'  - path: "{phase_dir_name}/PLACEHOLDER.md"\n'
        f'    hash: "{artifact_hash}"\n'
        f"approved: {str(approved).lower()}\n"
        f"approved_by: {approved_by_val}\n"
        f"approved_at: {approved_at_val}\n"
        f'drafted_at: "{_TS1}"\n'
        f"---\n",
        encoding="utf-8",
    )


@pytest.mark.integration
class TestPhaseGateSignoffRead:
    def test_phase1_approved_allows_phase2(self, tmp_path) -> None:
        _write_approved_record(tmp_path, phase=1)
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "allow"

    def test_phase1_awaiting_denies_phase2(self, tmp_path) -> None:
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "deny"
        assert "not found" in (result.reason or "")

    def test_phase1_drafted_not_approved_denies_phase2(self, tmp_path) -> None:
        _write_draft(tmp_path, phase=1, approved=False)
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "deny"
        assert "drafted but not yet approved" in (result.reason or "")

    def test_phase1_invalidated_denies_phase2(self, tmp_path) -> None:
        """INVALIDATED_BY_REPLAN must block further phase-2 writes (AC7, Task 7.2)."""
        _write_approved_record(tmp_path, phase=1)
        invalidate_record(
            1,
            repo_root=tmp_path,
            reason="replan triggered in test",
            now_utc=_TS3,
        )
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "deny"
        assert "invalidated by replan" in (result.reason or "")

    def test_reader_exception_denies(self, tmp_path) -> None:
        """Reader that raises a documented failure (SignoffError/OSError) → fail-safe deny.

        Per P30, programmer errors (RuntimeError, TypeError) now propagate so they
        surface real bugs rather than masking them as gate denials.
        """
        from sdlc.errors import SignoffError

        def _bad_reader(ph: int, rr) -> str:
            raise SignoffError("simulated disk error")

        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_bad_reader,
        )
        assert result.decision == "deny"
        assert "reader raised" in (result.reason or "")

    def test_phase2_approved_allows_phase3(self, tmp_path) -> None:
        _write_approved_record(tmp_path, phase=2)
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "allow"

    def test_phase2_awaiting_denies_phase3(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            signoff_reader=_reader(tmp_path),
        )
        assert result.decision == "deny"
        assert "not found" in (result.reason or "")

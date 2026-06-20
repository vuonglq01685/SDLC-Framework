"""Unit tests for engine/stop_replan_dirty.py (Story 4.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.engine.stop_replan_dirty import ReplanDirtyTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop
from sdlc.signoff import ArtifactRef, SignoffRecord, invalidate_record, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_NOW_UTC = "2026-06-18T10:00:00.000Z"


def _write_approved_signoffs(tmp_path: Path) -> None:
    for phase, rel in (
        (1, "01-Requirement/01-PRODUCT.md"),
        (2, "02-Architecture/ARCHITECTURE.md"),
    ):
        artifact_path = tmp_path / rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
        artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
        write_record(
            SignoffRecord(
                phase=phase,
                artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
                approved_by="test",
                approved_at=_NOW_UTC,
                drafted_at="2026-06-10T09:00:00.000Z",
                validated_at=_NOW_UTC,
            ),
            repo_root=tmp_path,
        )


def test_replan_dirty_trigger_satisfies_protocol() -> None:
    assert isinstance(ReplanDirtyTrigger(), StopTrigger)


def test_check_fires_when_phase_invalidated(tmp_path: Path) -> None:
    _write_approved_signoffs(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)
    trigger = ReplanDirtyTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "replan_dirty"
    assert decision.target == "phase-1"
    assert decision.reason is not None
    assert "phase-1" in decision.reason


def test_check_not_fired_when_no_invalidated_phase(tmp_path: Path) -> None:
    _write_approved_signoffs(tmp_path)
    trigger = ReplanDirtyTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_when_signoffs_dir_missing(tmp_path: Path) -> None:
    trigger = ReplanDirtyTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_both_phases_dirty_picks_lexical_first(tmp_path: Path) -> None:
    _write_approved_signoffs(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="r1", now_utc=_NOW_UTC)
    invalidate_record(2, repo_root=tmp_path, reason="r2", now_utc=_NOW_UTC)
    trigger = ReplanDirtyTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == "phase-1"
    assert decision.reason is not None
    assert "phase-1" in decision.reason
    assert "phase-2" in decision.reason


def test_malformed_record_propagates_signoff_error(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError

    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True)
    (signoff_dir / "phase-1.yaml").write_text("}{bad yaml}{", encoding="utf-8")
    trigger = ReplanDirtyTrigger()
    with pytest.raises(SignoffError):
        trigger.check(repo_root=tmp_path, state=State())


def test_multiplicity_re_sign_phase1_then_halt_on_phase2(tmp_path: Path) -> None:
    _write_approved_signoffs(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="r1", now_utc=_NOW_UTC)
    invalidate_record(2, repo_root=tmp_path, reason="r2", now_utc=_NOW_UTC)
    trigger = ReplanDirtyTrigger()

    first = trigger.check(repo_root=tmp_path, state=State())
    assert first.target == "phase-1"

    artifact_path = tmp_path / "01-Requirement/01-PRODUCT.md"
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=artifact_hash),),
            approved_by="test",
            approved_at=_NOW_UTC,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_NOW_UTC,
        ),
        repo_root=tmp_path,
    )

    second = trigger.check(repo_root=tmp_path, state=State())
    assert second.fired is True
    assert second.target == "phase-2"

    artifact_path2 = tmp_path / "02-Architecture/ARCHITECTURE.md"
    artifact_hash2 = compute_artifact_hash(artifact_path2, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=2,
            artifacts=(ArtifactRef(path="02-Architecture/ARCHITECTURE.md", hash=artifact_hash2),),
            approved_by="test",
            approved_at=_NOW_UTC,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_NOW_UTC,
        ),
        repo_root=tmp_path,
    )

    third = trigger.check(repo_root=tmp_path, state=State())
    assert third == StopDecision(fired=False)


def test_check_stop_fires_via_registry(tmp_path: Path) -> None:
    _write_approved_signoffs(tmp_path)
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "replan_dirty"


def test_compound_phase1_invalidated_phase2_unsigned_fires_phase1(tmp_path: Path) -> None:
    """CR4.3-W1 regression (review 2026-06-20): phase-1 INVALIDATED_BY_REPLAN combined with a
    genuinely-unsigned phase-2 (AWAITING_SIGNOFF) must fire on the dirty phase-1 only. An unsigned
    phase is NOT 'dirty' — only INVALIDATED_BY_REPLAN counts (C2). This is the compound state the
    4.3 review deferred to 4.5; pre-patch the suite only covered phase-2 APPROVED or both dirty.
    """
    # Sign + invalidate phase 1 ONLY; leave phase 2 unsigned → compute_state(2)==AWAITING_SIGNOFF.
    artifact_path = tmp_path / "01-Requirement/01-PRODUCT.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Phase 1\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=artifact_hash),),
            approved_by="test",
            approved_at=_NOW_UTC,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_NOW_UTC,
        ),
        repo_root=tmp_path,
    )
    invalidate_record(1, repo_root=tmp_path, reason="replan", now_utc=_NOW_UTC)

    decision = ReplanDirtyTrigger().check(repo_root=tmp_path, state=State())

    assert decision.fired is True
    assert decision.target == "phase-1"
    assert decision.reason is not None
    assert "phase-1" in decision.reason
    assert "phase-2" not in decision.reason  # unsigned phase-2 is awaiting-signoff, not dirty

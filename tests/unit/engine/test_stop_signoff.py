"""Unit tests for engine/stop_signoff.py (Story 4.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.engine.stop_signoff import SignoffRequiredTrigger
from sdlc.engine.stop_triggers import StopDecision, StopTrigger, check_stop
from sdlc.signoff import PHASE_DIR_MAP, ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.state.model import State

pytestmark = pytest.mark.unit

_TS = "2026-06-10T10:00:00.000Z"


def _write_phase1_started(repo_root: Path) -> None:
    product = repo_root / "01-Requirement" / "01-PRODUCT.md"
    product.parent.mkdir(parents=True, exist_ok=True)
    product.write_text("# Product\n", encoding="utf-8")


def _write_approved_signoff(repo_root: Path, phase: int, rel: str) -> None:
    artifact_path = repo_root / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=repo_root)
    write_record(
        SignoffRecord(
            phase=phase,
            artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
            approved_by="test",
            approved_at=_TS,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_TS,
        ),
        repo_root=repo_root,
    )


def _write_signoff_draft(repo_root: Path, phase: int, rel: str) -> Path:
    artifact_path = repo_root / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=repo_root)
    phase_dir = PHASE_DIR_MAP[phase]
    draft_path = repo_root / phase_dir / "SIGNOFF.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        f"""---
schema_version: 1
phase: {phase}
artifacts:
  - path: {rel}
    hash: {artifact_hash}
approved: false
approved_by: null
approved_at: null
drafted_at: 2026-06-10T09:00:00.000Z
---
""",
        encoding="utf-8",
    )
    return draft_path


def _write_invalidated_signoff(repo_root: Path, phase: int, rel: str) -> None:
    artifact_path = repo_root / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=repo_root)
    write_record(
        SignoffRecord(
            phase=phase,
            artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
            approved_by="test",
            approved_at=_TS,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_TS,
            invalidated_at="2026-06-11T10:00:00.000Z",
            invalidated_reason="replan",
        ),
        repo_root=repo_root,
    )


def _write_malformed_signoff_draft(repo_root: Path, phase: int, rel: str) -> None:
    """A SIGNOFF.md draft whose ``approved`` is not a YAML boolean.

    ``compute_state`` propagates the resulting ``SignoffError`` for this
    operator-actionable case rather than demoting it to ``AWAITING_SIGNOFF``
    (``signoff/states.py:57-60,89-98``).
    """
    artifact_path = repo_root / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    draft_path = repo_root / PHASE_DIR_MAP[phase] / "SIGNOFF.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        "---\nschema_version: 1\nphase: 1\napproved: not-a-bool\n---\n",
        encoding="utf-8",
    )


def test_signoff_required_trigger_satisfies_protocol() -> None:
    assert isinstance(SignoffRequiredTrigger(), StopTrigger)


def test_check_fires_on_awaiting_signoff(tmp_path: Path) -> None:
    _write_phase1_started(tmp_path)
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "signoff_required"
    assert decision.target == "01-Requirement/SIGNOFF.md"
    assert decision.reason is not None
    assert "phase 1" in decision.reason
    assert "awaiting-signoff" in decision.reason
    assert "/sdlc-signoff 1" in decision.reason


def test_check_fires_on_drafted_not_approved(tmp_path: Path) -> None:
    _write_phase1_started(tmp_path)
    _write_signoff_draft(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "signoff_required"
    assert decision.target == "01-Requirement/SIGNOFF.md"
    assert decision.reason is not None
    assert "drafted-not-approved" in decision.reason


def test_check_not_fired_when_all_phases_approved(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    _write_approved_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_not_fired_on_invalidated_by_replan(tmp_path: Path) -> None:
    _write_invalidated_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)


def test_check_fires_on_phase2_when_phase1_approved(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.target == "02-Architecture/SIGNOFF.md"
    assert decision.reason is not None
    assert "phase 2" in decision.reason


def test_check_stop_fires_via_registry(tmp_path: Path) -> None:
    _write_phase1_started(tmp_path)
    decision = check_stop(repo_root=tmp_path, state=State())
    assert decision.fired is True
    assert decision.trigger == "signoff_required"


def test_check_fails_open_on_malformed_draft(tmp_path: Path) -> None:
    """Fail-open disposition (review 2026-06-20, decision option 1).

    A corrupt/unreadable signoff makes ``compute_state`` raise ``SignoffError``;
    the trigger swallows it and returns ``fired=False`` rather than crashing the
    loop. This locks the chosen policy so the silent no-halt is a tested,
    deliberate choice (see Change Log + story Review Findings).
    """
    _write_malformed_signoff_draft(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    trigger = SignoffRequiredTrigger()
    decision = trigger.check(repo_root=tmp_path, state=State())
    assert decision == StopDecision(fired=False)

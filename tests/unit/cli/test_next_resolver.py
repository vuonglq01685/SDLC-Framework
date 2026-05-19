"""Unit tests for cli/_next_resolver.py:resolve_next (Story 2A.18, AC2, AC4, AC5, Task 2.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.cli._next_resolver import resolve_next

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID_1 = f"{_STORY_ID}-T01-first-task"
_TASK_ID_2 = f"{_STORY_ID}-T02-second-task"


def _write_approved_signoff(tmp_path: Path, phase: int) -> None:
    """Write a minimal approved signoff record for the given phase."""
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    # Need a real artifact for the hash
    if phase == 1:
        artifact_rel = "01-Requirement/01-PRODUCT.md"
        artifact_path = tmp_path / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("# Product\nTest content.", encoding="utf-8")
    else:
        artifact_rel = "02-Architecture/ARCHITECTURE.md"
        artifact_path = tmp_path / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("# Architecture\nTest content.", encoding="utf-8")

    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_rel, hash=artifact_hash),),
        approved_by="test-approver",
        approved_at="2026-05-18T10:00:00.000Z",
        drafted_at="2026-05-18T09:00:00.000Z",
        validated_at="2026-05-18T10:00:00.000Z",
    )
    write_record(record, repo_root=tmp_path)


def _write_product_md(tmp_path: Path) -> None:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Product\nContent.", encoding="utf-8")


def _write_epic_json(tmp_path: Path, epic_id: str = _EPIC_ID) -> Path:
    epics_dir = tmp_path / "01-Requirement" / "04-Epics"
    epics_dir.mkdir(parents=True, exist_ok=True)
    p = epics_dir / f"{epic_id}.json"
    p.write_text(json.dumps({"id": epic_id}), encoding="utf-8")
    return p


def _write_story_json(tmp_path: Path, epic_id: str = _EPIC_ID, story_id: str = _STORY_ID) -> Path:
    stories_dir = tmp_path / "01-Requirement" / "05-Stories" / epic_id
    stories_dir.mkdir(parents=True, exist_ok=True)
    p = stories_dir / f"{story_id}.json"
    p.write_text(json.dumps({"id": story_id}), encoding="utf-8")
    return p


def _write_arch_md(tmp_path: Path) -> Path:
    arch_dir = tmp_path / "02-Architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)
    p = arch_dir / "ARCHITECTURE.md"
    p.write_text("# Architecture\nContent.", encoding="utf-8")
    return p


def _write_task_json(
    tmp_path: Path,
    task_id: str = _TASK_ID_1,
    story_id: str = _STORY_ID,
    *,
    stage: str = "pending",
    dependencies: list[str] | None = None,
) -> Path:
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / story_id
    tasks_dir.mkdir(parents=True, exist_ok=True)
    # Extract filename from task_id (T01-first-task)
    parts = task_id.split("-T", 1)
    fname = "T" + parts[1] + ".json" if len(parts) == 2 else f"{task_id}.json"
    p = tasks_dir / fname
    entry = {
        "id": task_id,
        "story_id": story_id,
        "label": "Test task",
        "stage": stage,
        "dependencies": dependencies or [],
        "review_verdict": None,
        "review_notes": None,
    }
    p.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Step 1: PRODUCT.md absent → /sdlc-start
# ---------------------------------------------------------------------------


def test_product_md_absent_suggests_sdlc_start(tmp_path: Path) -> None:
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert "/sdlc-start" in (decision.command or "")
    assert decision.phase == 1


# ---------------------------------------------------------------------------
# Step 2: Phase 1 unsigned (artifacts present) → /sdlc-signoff 1
# ---------------------------------------------------------------------------


def test_phase1_unsigned_with_all_artifacts_suggests_signoff1(tmp_path: Path) -> None:
    _write_product_md(tmp_path)
    _write_epic_json(tmp_path)
    _write_story_json(tmp_path)
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert decision.command == "/sdlc-signoff 1"
    assert decision.phase == 1


# ---------------------------------------------------------------------------
# Step 2: Phase 1 no epics → /sdlc-epics
# ---------------------------------------------------------------------------


def test_phase1_no_epics_suggests_sdlc_epics(tmp_path: Path) -> None:
    _write_product_md(tmp_path)
    # No epic JSONs
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert decision.command == "/sdlc-epics"
    assert decision.phase == 1


# ---------------------------------------------------------------------------
# Step 2: Phase 1 epic without stories → /sdlc-stories <EPIC-id>
# ---------------------------------------------------------------------------


def test_phase1_epic_without_stories_suggests_sdlc_stories(tmp_path: Path) -> None:
    _write_product_md(tmp_path)
    _write_epic_json(tmp_path)
    # No story for EPIC-myepic
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert decision.command == f"/sdlc-stories {_EPIC_ID}"
    assert decision.phase == 1


# ---------------------------------------------------------------------------
# Step 3: Phase 2 unsigned, no architecture artifact → /sdlc-architect
# ---------------------------------------------------------------------------


def test_phase2_no_arch_suggests_sdlc_architect(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert decision.command == "/sdlc-architect"
    assert decision.phase == 2


# ---------------------------------------------------------------------------
# Step 3: Phase 2 arch present but unsigned → /sdlc-signoff 2
# ---------------------------------------------------------------------------


def test_phase2_arch_present_unsigned_suggests_signoff2(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    _write_arch_md(tmp_path)
    decision = resolve_next(tmp_path)
    assert decision.kind == "run_command"
    assert decision.command == "/sdlc-signoff 2"
    assert decision.phase == 2


# ---------------------------------------------------------------------------
# Step 4: Phase 2 APPROVED, pending dep-satisfied task → dispatch_task
# ---------------------------------------------------------------------------


def test_phase2_approved_pending_task_dispatches(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_task_json(tmp_path, stage="pending")
    decision = resolve_next(tmp_path)
    assert decision.kind == "dispatch_task"
    assert decision.task_id == _TASK_ID_1


# ---------------------------------------------------------------------------
# Step 4: T02 depends on non-done T01 → resolver selects T01
# ---------------------------------------------------------------------------


def test_dependency_gate_selects_earlier_dep_first(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_task_json(tmp_path, task_id=_TASK_ID_1, stage="pending", dependencies=[])
    _write_task_json(tmp_path, task_id=_TASK_ID_2, stage="pending", dependencies=[_TASK_ID_1])
    decision = resolve_next(tmp_path)
    assert decision.kind == "dispatch_task"
    assert decision.task_id == _TASK_ID_1


# ---------------------------------------------------------------------------
# Step 4: All tasks done → no-ready-items
# ---------------------------------------------------------------------------


def test_all_tasks_done_returns_none(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _write_task_json(tmp_path, stage="done")
    decision = resolve_next(tmp_path)
    assert decision.kind == "none"
    assert "complete" in decision.reason


# ---------------------------------------------------------------------------
# Step 4: All tasks blocked (T01 done, T02 dep on missing T03) → none with blockers
# ---------------------------------------------------------------------------


def test_all_tasks_blocked_returns_none_with_blockers(tmp_path: Path) -> None:
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)
    _task_id_missing = f"{_STORY_ID}-T03-missing-dep"
    _write_task_json(tmp_path, task_id=_TASK_ID_1, stage="pending", dependencies=[_task_id_missing])
    decision = resolve_next(tmp_path)
    assert decision.kind == "none"
    assert decision.blockers.get("blocked_by_deps", 0) >= 1

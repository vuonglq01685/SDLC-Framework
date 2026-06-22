"""Shared fixtures for engine/auto_loop unit tests (Story 4.1 / 4.11).

Lives directly under ``tests/`` and is importable as ``from _auto_loop_helpers import ...``
because ``tests/conftest.py`` puts ``tests/`` on ``sys.path`` (same seam as ``_clihelper``).
Extracted from ``test_auto_loop.py`` so the mad-mode seam tests can split into a sibling
file without either module breaching the 400-LOC cap (NFR-MAINT-3).
"""

from __future__ import annotations

import json
from pathlib import Path

from sdlc.runtime.mock import MockAIRuntime

_EPIC_ID = "EPIC-myepic"
_STORY_ID = f"{_EPIC_ID}-S01-my-story"
_TASK_ID = f"{_STORY_ID}-T01-first-task"


def _mock_runtime(tmp_path: Path) -> MockAIRuntime:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return MockAIRuntime(fixtures_dir=fixtures)


def _write_approved_signoffs(tmp_path: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

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
                approved_at="2026-06-10T10:00:00.000Z",
                drafted_at="2026-06-10T09:00:00.000Z",
                validated_at="2026-06-10T10:00:00.000Z",
            ),
            repo_root=tmp_path,
        )


def _write_phase3_ready_project(tmp_path: Path, *, stage: str = "pending") -> None:
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    epics = tmp_path / "01-Requirement" / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / f"{_EPIC_ID}.json").write_text(json.dumps({"id": _EPIC_ID}), encoding="utf-8")
    stories = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    stories.mkdir(parents=True, exist_ok=True)
    (stories / f"{_STORY_ID}.json").write_text(json.dumps({"id": _STORY_ID}), encoding="utf-8")
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    tasks = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-first-task.json").write_text(
        json.dumps(
            {
                "id": _TASK_ID,
                "story_id": _STORY_ID,
                "label": "t",
                "stage": stage,
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )
    _write_approved_signoffs(tmp_path)


def _bootstrap_journal(tmp_path: Path) -> tuple[Path, Path]:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    journal = (state_dir / "journal.log").resolve()
    journal.touch()
    state = (state_dir / "state.json").resolve()
    state.write_text("{}", encoding="utf-8")
    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").resolve()
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.touch()
    return journal, runs


def _write_phase1_approved_phase2_unsigned_project(tmp_path: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    epics = tmp_path / "01-Requirement" / "04-Epics"
    epics.mkdir(parents=True, exist_ok=True)
    (epics / f"{_EPIC_ID}.json").write_text(json.dumps({"id": _EPIC_ID}), encoding="utf-8")
    stories = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    stories.mkdir(parents=True, exist_ok=True)
    (stories / f"{_STORY_ID}.json").write_text(json.dumps({"id": _STORY_ID}), encoding="utf-8")
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "02-Architecture" / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    tasks = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "T01-first-task.json").write_text(
        json.dumps(
            {
                "id": _TASK_ID,
                "story_id": _STORY_ID,
                "label": "t",
                "stage": "pending",
                "dependencies": [],
                "review_verdict": None,
                "review_notes": None,
            }
        ),
        encoding="utf-8",
    )
    p1 = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    h1 = compute_artifact_hash(p1, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=h1),),
            approved_by="test",
            approved_at="2026-06-10T10:00:00.000Z",
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at="2026-06-10T10:00:00.000Z",
        ),
        repo_root=tmp_path,
    )

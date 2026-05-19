"""Integration tests for ``sdlc task`` — TDD pipeline (Story 2A.17, AC1-AC10, Task 4.4)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.integration

_runner = CliRunner()

_STORY_ID = "EPIC-testprod-S01-user-auth"
_EPIC_ID = "EPIC-testprod"
_TASK_ID = "EPIC-testprod-S01-user-auth-T01-design-data-model"

_TS1 = "2026-05-18T09:00:00.000Z"
_TS2 = "2026-05-18T10:00:00.000Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_approved_phase2(tmp_path: Path) -> None:
    artifact_path = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Product\n", encoding="utf-8")

    for phase in (1, 2):
        ref = ArtifactRef(
            path="01-Requirement/01-PRODUCT.md",
            hash=compute_artifact_hash(artifact_path, repo_root=tmp_path),
        )
        rec = SignoffRecord(
            phase=phase,
            artifacts=(ref,),
            approved_by="integration-test",
            approved_at=_TS2,
            drafted_at=_TS1,
            validated_at=_TS2,
        )
        write_record(rec, repo_root=tmp_path)


def _write_story(tmp_path: Path) -> Path:
    data = {
        "schema_version": 1,
        "id": _STORY_ID,
        "epic_id": _EPIC_ID,
        "seq": 1,
        "label": "User auth story",
        "as_a": "developer",
        "i_want": "auth",
        "so_that": "users log in",
        "given_when_then": ["Given setup, when login, then token."],
        "dependencies": [],
        "drafted_at": "2026-05-18T09:00:00Z",
        "drafted_by_specialist": "test",
    }
    p = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID / f"{_STORY_ID}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def _task_json(
    *,
    stage: str = "pending",
    review_verdict: str | None = None,
    review_notes: str | None = None,
) -> str:
    data: dict[str, object] = {
        "id": _TASK_ID,
        "story_id": _STORY_ID,
        "label": "Design the data model.",
        "stage": stage,
        "dependencies": [],
        "review_verdict": review_verdict,
        "review_notes": review_notes,
    }
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _write_task(
    tmp_path: Path,
    *,
    stage: str = "pending",
    review_verdict: str | None = None,
    review_notes: str | None = None,
) -> Path:
    p = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_task_json(stage=stage, review_verdict=review_verdict, review_notes=review_notes))
    return p


def _invoke_task(tmp_path: Path, task_id: str = _TASK_ID) -> object:
    with unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, ["--json", "task", task_id])


def _setup_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_approved_phase2(tmp_path)
    _write_story(tmp_path)


def _journal_kinds(tmp_path: Path) -> list[str]:
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    return [json.loads(line)["kind"] for line in journal.strip().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Integration test: Full pipeline drive (AC11 scenario 1)
# ---------------------------------------------------------------------------


def test_full_pipeline_drive_four_invocations(tmp_path: Path) -> None:
    """Drive task from pending → done in 4 invocations (AC11 scenario 1)."""
    _setup_repo(tmp_path)
    _write_task(tmp_path, stage="pending")

    test_files_output = json.dumps(
        {
            "files": [{"path": "tests/unit/test_design.py", "content": "# test"}],
            "tests_status": "red",
        }
    )
    code_files_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/design.py", "content": "# impl"}],
            "tests_status": "green",
        }
    )
    review_output = json.dumps({"verdict": "approved", "notes": "LGTM"})

    stages = ["pending", "write-tests", "write-code", "review"]
    outputs = [test_files_output, code_files_output, review_output, None]

    with unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path):
        for _i, (stage, mock_output) in enumerate(zip(stages, outputs, strict=True)):
            if mock_output:
                dispatch_result = unittest.mock.MagicMock()
                dispatch_result.outcome = "success"
                dispatch_result.agent_result.output_text = mock_output
                with unittest.mock.patch(
                    "sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result
                ):
                    r = _runner.invoke(app, ["--json", "task", _TASK_ID])
            else:
                r = _runner.invoke(app, ["--json", "task", _TASK_ID])
            assert r.exit_code == 0, f"Stage {stage} failed: {r.output}"

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "done"
    assert task_data["review_verdict"] == "approved"

    # Journal has exactly 4 task_stage_advanced entries
    kinds = _journal_kinds(tmp_path)
    advanced = [k for k in kinds if k == "task_stage_advanced"]
    assert len(advanced) == 4

    # Test file under tests/, code file under src/
    assert (tmp_path / "tests" / "unit" / "test_design.py").exists()
    assert (tmp_path / "src" / "sdlc" / "design.py").exists()


# ---------------------------------------------------------------------------
# Integration test: Idempotency — done refuse (AC11 scenario 2)
# ---------------------------------------------------------------------------


def test_done_task_refused_no_dispatch(tmp_path: Path) -> None:
    """Task at done refuses with non-zero exit; no dispatch (AC11 scenario 2)."""
    _setup_repo(tmp_path)
    _write_task(tmp_path, stage="done", review_verdict="approved", review_notes="OK")

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch") as mock_dispatch,
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    assert "task already complete" in r.output.lower() or "done" in r.output.lower()
    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Integration test: Rejected review stays at review (AC11 scenario 3)
# ---------------------------------------------------------------------------


def test_rejected_review_stays_at_review_stage(tmp_path: Path) -> None:
    """Rejected review: non-zero exit, stays at review, task_stage_failed journaled (AC11.3)."""
    _setup_repo(tmp_path)
    _write_task(tmp_path, stage="review", review_verdict="rejected", review_notes="needs work")

    r = _invoke_task(tmp_path)

    assert r.exit_code != 0
    assert "rejected" in r.output.lower() or "review" in r.output.lower()

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "review"

    kinds = _journal_kinds(tmp_path)
    assert "task_stage_failed" in kinds


# ---------------------------------------------------------------------------
# Integration test: RED→GREEN gate (AC11 scenario 4)
# ---------------------------------------------------------------------------


def test_red_green_gate_code_author_still_red(tmp_path: Path) -> None:
    """Code-author returns red: non-zero exit, stage unchanged, files rolled back (AC11.4)."""
    _setup_repo(tmp_path)
    _write_task(tmp_path, stage="write-tests")

    code_files_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/design.py", "content": "# impl"}],
            "tests_status": "red",
        }
    )
    dispatch_result = unittest.mock.MagicMock()
    dispatch_result.outcome = "success"
    dispatch_result.agent_result.output_text = code_files_output

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    assert "GREEN" in r.output or "green" in r.output.lower() or "red" in r.output.lower()

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "write-tests"

    assert not (tmp_path / "src" / "sdlc" / "design.py").exists()

    kinds = _journal_kinds(tmp_path)
    assert "task_stage_failed" in kinds

    journal_log = tmp_path / ".claude" / "state" / "journal.log"
    failed_entries = [
        json.loads(line)
        for line in journal_log.read_text().strip().splitlines()
        if '"task_stage_failed"' in line
    ]
    assert any(
        "green" in str(e.get("payload", {}).get("reason", "")).lower() for e in failed_entries
    )

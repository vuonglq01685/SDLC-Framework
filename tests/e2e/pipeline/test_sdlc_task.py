"""Tier-2 e2e for ``sdlc task`` — TDD pipeline (Story 2A.17, AC11, Task 5).

AC11 mandates FOUR scenarios. All are driven through the real MockAIRuntime
pipeline (no ``dispatch`` mock for the happy path):

  1. Happy path: full pipeline drive — pending → done in 4 invocations via
     real MockAIRuntime; journal has 4 ``task_stage_advanced`` entries;
     test file under tests/ and impl file under src/ are written.
  2. Idempotency: task at ``done`` refuses with exit 1; no dispatch.
  3. Rejected review: task at ``review`` with ``review_verdict="rejected"``
     → exit 1, stage stays ``review``, ``task_stage_failed`` journaled.
  4. RED→GREEN gate: code-author returns ``tests_status="red"`` → exit 1,
     stage stays ``write-tests``, impl file rolled back.

Anti-tautology receipt (AC11 mandatory — executable form):
  ``test_e2e_task_review_verdict_gate_is_load_bearing``: wraps
  ``task_stage_dispatch_write`` to substitute the task's ``review_verdict``
  with ``"approved"`` at the review stage, then re-runs a "rejected" task.
  With the gate neutralised the command MUST succeed (exit 0) and advance to
  ``done`` — proving the verdict check, and only it, causes that refusal.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "task"

_STORY_ID = "EPIC-e2etask-S01-user-auth"
_EPIC_ID = "EPIC-e2etask"
_TASK_ID = "EPIC-e2etask-S01-user-auth-T01-design-data-model"

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


def _seed_product_md(tmp_path: Path) -> Path:
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    p = req / "01-PRODUCT.md"
    p.write_bytes((_FIXTURES / "01-PRODUCT.md").read_bytes())
    return p


def _approve_phase(tmp_path: Path, phase: int, artifact_path: Path, artifact_key: str) -> None:
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_key, hash=artifact_hash),),
        approved_by="e2e-approver",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _seed_story_json(tmp_path: Path) -> Path:
    src = _FIXTURES / f"{_STORY_ID}.json"
    story_dir = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    story_dir.mkdir(parents=True, exist_ok=True)
    p = story_dir / f"{_STORY_ID}.json"
    p.write_bytes(src.read_bytes())
    return p


def _write_task(
    tmp_path: Path,
    *,
    stage: str = "pending",
    review_verdict: str | None = None,
    review_notes: str | None = None,
) -> Path:
    data: dict[str, object] = {
        "id": _TASK_ID,
        "story_id": _STORY_ID,
        "label": "Design the data model.",
        "stage": stage,
        "dependencies": [],
        "review_verdict": review_verdict,
        "review_notes": review_notes,
    }
    p = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _invoke_task(tmp_path: Path, task_id: str = _TASK_ID) -> Any:
    with unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, ["--json", "task", task_id])


def _ready_approved_repo(tmp_path: Path) -> None:
    """Init + phase-1/2 signoffs via product.md."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, product_path, "01-Requirement/01-PRODUCT.md")


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: full pipeline drive (AC11.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_task_full_pipeline_drive(tmp_path: Path) -> None:
    """AC11 scenario 1: full pipeline drive — pending → done in 4 invocations.

    Uses real MockAIRuntime (SDLC_USE_MOCK_RUNTIME=1 default); no dispatch mock.
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    _write_task(tmp_path, stage="pending")

    for i in range(4):
        r = _invoke_task(tmp_path)
        assert r.exit_code == 0, f"invocation {i + 1} failed: {r.output}"

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "done"
    assert task_data["review_verdict"] == "approved"

    entries = _read_journal(tmp_path)
    advanced = [e for e in entries if e.get("kind") == "task_stage_advanced"]
    kinds_seen = [e["kind"] for e in entries]
    assert len(advanced) == 4, f"expected 4 task_stage_advanced; got {kinds_seen}"
    assert "task_stage_failed" not in kinds_seen, (
        f"a clean full-pipeline drive must journal no failures; got {kinds_seen}"
    )

    # Real mock runtime writes: test file under tests/, impl file under src/
    task_num_part = _TASK_ID.rsplit("-T", maxsplit=1)[-1].split("-", maxsplit=1)[0]  # "01"
    assert (tmp_path / "tests" / "unit" / f"test_{task_num_part}.py").exists()
    assert (tmp_path / "src" / "sdlc" / f"impl_{task_num_part}.py").exists()


# ---------------------------------------------------------------------------
# Scenario 2 — Idempotency: done task refuses (AC11.2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_task_done_refused_no_dispatch(tmp_path: Path) -> None:
    """AC11 scenario 2: task at done refuses with exit 1; no dispatch."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    _write_task(tmp_path, stage="done", review_verdict="approved", review_notes="OK")

    with unittest.mock.patch("sdlc.cli._task_pipeline.dispatch") as mock_dispatch:
        r = _invoke_task(tmp_path)

    assert r.exit_code != 0
    out_lower = r.output.lower()
    assert "done" in out_lower or "already" in out_lower or "complete" in out_lower
    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3 — Rejected review stays at review (AC11.3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_task_rejected_review_stays_at_review(tmp_path: Path) -> None:
    """AC11 scenario 3: rejected review → exit 1, stage stays review, failure journaled."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    _write_task(tmp_path, stage="review", review_verdict="rejected", review_notes="needs work")

    r = _invoke_task(tmp_path)

    assert r.exit_code != 0
    assert "review rejected for" in r.output.lower()

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "review"

    entries = _read_journal(tmp_path)
    kinds = [e.get("kind") for e in entries]
    assert "task_stage_failed" in kinds


# ---------------------------------------------------------------------------
# Scenario 4 — RED→GREEN gate: code-author returns red (AC11.4)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_task_red_green_gate_code_author_still_red(tmp_path: Path) -> None:
    """AC11 scenario 4: code-author returns red → exit 1, stage unchanged, impl file rolled back."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    _write_task(tmp_path, stage="write-tests")

    red_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/design.py", "content": "# impl"}],
            "tests_status": "red",
        }
    )
    dispatch_result = unittest.mock.MagicMock()
    dispatch_result.outcome = "success"
    dispatch_result.agent_result.output_text = red_output

    with unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result):
        r = _invoke_task(tmp_path)

    assert r.exit_code != 0
    assert "did not turn the test suite green" in r.output.lower()

    task_file = tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"
    task_data = json.loads(task_file.read_text())
    assert task_data["stage"] == "write-tests"

    # Impl file rolled back
    assert not (tmp_path / "src" / "sdlc" / "design.py").exists()

    entries = _read_journal(tmp_path)
    kinds = [e.get("kind") for e in entries]
    assert "task_stage_failed" in kinds


# ---------------------------------------------------------------------------
# Anti-tautology receipt: review_verdict gate is load-bearing (AC11)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_task_review_verdict_gate_is_load_bearing(tmp_path: Path) -> None:
    """AC11 anti-tautology receipt (executable form).

    Mutation: wrap ``task_stage_dispatch_write`` to replace the task's
    ``review_verdict`` with ``"approved"`` at the review stage, then run with
    a task where ``review_verdict="rejected"`` (normally blocked at the gate).
    With the gate neutralised the command MUST succeed (exit 0) and the stage
    MUST advance to ``done`` — proving the verdict check, and only it, is the
    barrier in scenario 3.
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    task_path = _write_task(
        tmp_path, stage="review", review_verdict="rejected", review_notes="needs work"
    )

    # Baseline: rejected task must fail
    result_normal = _invoke_task(tmp_path)
    assert result_normal.exit_code != 0, "baseline: rejected review must fail before mutation"
    assert "rejected" in (result_normal.stdout + (result_normal.stderr or "")).lower(), (
        "baseline: 'rejected' must appear in output before mutation"
    )

    # Re-seed task with rejected verdict (stage did not advance)
    task_path = _write_task(
        tmp_path, stage="review", review_verdict="rejected", review_notes="needs work"
    )

    # Neutralise: wrap dispatch_write to substitute review_verdict → "approved" at review stage
    import sdlc.cli._task_pipeline as _pipeline

    _real_dispatch_write = _pipeline.task_stage_dispatch_write

    async def _neutralized_dispatch_write(**kwargs: Any) -> str | None:
        task = kwargs.get("task")
        if task is not None and task.stage == "review":
            kwargs["task"] = task.model_copy(update={"review_verdict": "approved"})
        return await _real_dispatch_write(**kwargs)

    # Patch the name in task.py's namespace (that's where asyncio.run calls it).
    with (
        unittest.mock.patch(
            "sdlc.cli.task.task_stage_dispatch_write",
            side_effect=_neutralized_dispatch_write,
        ),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        result_mutated = _runner.invoke(app, ["--json", "task", _TASK_ID])

    out_text = result_mutated.stdout + (result_mutated.stderr or "")
    assert "rejected" not in out_text.lower(), (
        "anti-tautology breach: 'rejected' error still raised with verdict gate neutralised"
    )
    assert result_mutated.exit_code == 0, (
        f"with verdict gate neutralised the command must succeed; got: {out_text}"
    )

    task_data = json.loads(task_path.read_text())
    assert task_data["stage"] == "done", (
        f"stage must advance to 'done' after gate neutralised; got {task_data['stage']}"
    )

"""Integration tests for sdlc next (Story 2A.18, AC3-AC5, Task 3.3).

Tests run_next end-to-end against a tmp repo at each phase boundary.
MockAIRuntime is NOT used here; we assert routing decisions only.
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.integration

_runner = CliRunner()

# Stable identifiers matching _next_resolver._EPIC_ID conventions
_EPIC_ID = "EPIC-inttest"
_STORY_ID = f"{_EPIC_ID}-S01-user-login"
_TASK_ID = f"{_STORY_ID}-T01-write-tests"


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _invoke(tmp_path: Path, *, json_out: bool = False) -> object:
    args = ["--json", "next"] if json_out else ["next"]
    with unittest.mock.patch("sdlc.cli.next_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _approve_phase(tmp_path: Path, phase: int, artifact_rel: str) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    artifact_path = tmp_path / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if not artifact_path.exists():
        artifact_path.write_text("# Content\n", encoding="utf-8")

    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_rel, hash=artifact_hash),),
        approved_by="integration-approver",
        approved_at="2026-05-18T10:00:00.000Z",
        drafted_at="2026-05-18T09:00:00.000Z",
        validated_at="2026-05-18T10:00:00.000Z",
    )
    write_record(record, repo_root=tmp_path)


def _write_product_md(tmp_path: Path) -> None:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Product Brief\nContent.", encoding="utf-8")


def _write_task_json(
    tmp_path: Path,
    *,
    stage: str = "pending",
    dependencies: list[str] | None = None,
) -> Path:
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks_dir.mkdir(parents=True, exist_ok=True)
    fname = "T01-write-tests.json"
    entry = {
        "id": _TASK_ID,
        "story_id": _STORY_ID,
        "label": "Write tests",
        "stage": stage,
        "dependencies": dependencies or [],
        "review_verdict": None,
        "review_notes": None,
    }
    p = tasks_dir / fname
    p.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Phase boundary: not initialized
# ---------------------------------------------------------------------------


def test_not_initialized_exits_nonzero(tmp_path: Path) -> None:
    r = _invoke(tmp_path)
    assert r.exit_code != 0


# ---------------------------------------------------------------------------
# Phase boundary: phase 1 not started (no PRODUCT.md)
# ---------------------------------------------------------------------------


def test_phase1_not_started_suggests_sdlc_start(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke(tmp_path, json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["next_action"] == "command"
    assert "/sdlc-start" in data["suggested_command"]


# ---------------------------------------------------------------------------
# Phase boundary: phase 2 unsigned (phase 1 approved but no arch)
# ---------------------------------------------------------------------------


def test_phase2_not_started_suggests_sdlc_architect(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    _approve_phase(tmp_path, phase=1, artifact_rel="01-Requirement/01-PRODUCT.md")
    r = _invoke(tmp_path, json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["next_action"] == "command"
    assert "/sdlc-architect" in data["suggested_command"]


# ---------------------------------------------------------------------------
# Phase boundary: phase 2 approved, no task JSONs → none (no tasks generated yet)
# ---------------------------------------------------------------------------


def test_phase2_approved_no_tasks_returns_none(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    _approve_phase(tmp_path, phase=1, artifact_rel="01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, phase=2, artifact_rel="02-Architecture/ARCHITECTURE.md")
    r = _invoke(tmp_path, json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["next_action"] == "none"
    # No task JSON exists yet — the reason must say so, not "all tasks complete".
    assert "no tasks" in data["reason"], (
        f"expected a 'no tasks generated' reason; got {data['reason']!r}"
    )


# ---------------------------------------------------------------------------
# Phase boundary: phase 2 approved, pending task → run_task called
# ---------------------------------------------------------------------------


def test_phase2_approved_pending_task_calls_run_task(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    _approve_phase(tmp_path, phase=1, artifact_rel="01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, phase=2, artifact_rel="02-Architecture/ARCHITECTURE.md")
    _write_task_json(tmp_path, stage="pending")

    with unittest.mock.patch("sdlc.cli.task.run_task") as mock_run_task:
        _invoke(tmp_path)
    mock_run_task.assert_called_once()
    call_kwargs = mock_run_task.call_args.kwargs
    assert call_kwargs["task_id"] == _TASK_ID

"""Unit tests for cli/break_.py:run_break (Story 2A.16, AC1-AC6, AC8, Task 4.1)."""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()

_STORY_ID = "EPIC-foo-S01-bar"
_EPIC_ID = "EPIC-foo"
_PRODUCT_CONTENT = "# Product Brief\n\n## Overview\n\nA product for testing.\n"

# ---------------------------------------------------------------------------
# Helper: story JSON body
# ---------------------------------------------------------------------------

_BASE_STORY: dict = {
    "schema_version": 1,
    "id": _STORY_ID,
    "epic_id": _EPIC_ID,
    "seq": 1,
    "label": "Break story into tasks",
    "as_a": "developer",
    "i_want": "to break the story into tasks",
    "so_that": "I can implement each task independently",
    "given_when_then": ["Given a story, when I run break, then tasks are created."],
    "dependencies": [],
    "drafted_at": "2026-05-18T10:00:00Z",
    "drafted_by_specialist": "test-specialist",
}


def _story_json(*, status: str = "in-progress") -> str:
    data = dict(_BASE_STORY)
    data["status"] = status
    return json.dumps(data, sort_keys=True, indent=2)


def _story_path(tmp_path: Path) -> Path:
    return tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID / f"{_STORY_ID}.json"


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    import typer

    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_approved_signoff(tmp_path: Path, phase: int) -> None:
    signoffs_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "phase": phase,
        "artifacts": [
            {
                "schema_version": 1,
                "path": f"0{phase}-artifact/artifact.md",
                "hash": "sha256:" + "a" * 64,
            }
        ],
        "approved_by": "test-approver",
        "approved_at": "2026-05-17T10:00:00.000Z",
        "drafted_at": "2026-05-17T09:00:00.000Z",
        "validated_at": "2026-05-17T10:00:00.000Z",
    }
    (signoffs_dir / f"phase-{phase}.yaml").write_text(
        yaml.safe_dump(record, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _write_product_md(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content is not None else _PRODUCT_CONTENT, encoding="utf-8")
    return p


def _write_story(tmp_path: Path, *, status: str = "in-progress", raw: str | None = None) -> Path:
    p = _story_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw if raw is not None else _story_json(status=status), encoding="utf-8")
    return p


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _invoke_break(tmp_path: Path, story_id: str = _STORY_ID, *, json_mode: bool = True) -> object:
    args = ["--json", "break", story_id] if json_mode else ["break", story_id]
    with unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _ready_repo(tmp_path: Path) -> None:
    """Init + signoffs + PRODUCT.md + active story."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    _write_story(tmp_path, status="in-progress")


def _three_task_batch(story_id: str = _STORY_ID) -> str:
    from sdlc.cli._break_pipeline import mock_task_batch_body

    return mock_task_batch_body(story_id)


# ---------------------------------------------------------------------------
# AC1 — Story ID format validation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_invalid_story_id_format_raises(tmp_path: Path) -> None:
    """AC1: story_id not matching STORY_ID_REGEX → ERR_USER_INPUT, exit 1."""
    _init_repo(tmp_path)
    r = _invoke_break(tmp_path, story_id="not-a-valid-story-id")
    assert r.exit_code == 1
    out = r.stdout + (r.stderr or "")
    assert "ERR_USER_INPUT" in out and "invalid story-id" in out.lower()


# ---------------------------------------------------------------------------
# AC1 — Phase 2 gate
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_phase2_not_approved_raises(tmp_path: Path) -> None:
    """AC1: no phase-2 signoff → ERR_PHASE2_NOT_APPROVED, no files written."""
    _init_repo(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch") as mock_dispatch,
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "ERR_PHASE2_NOT_APPROVED" in (r.stdout + (r.stderr or ""))
    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# AC2 — Story-level gate
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_story_not_found_raises(tmp_path: Path) -> None:
    """AC2: story JSON missing → error 'story not found', exit 1."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    # intentionally do NOT write story file

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    out = r.stdout + (r.stderr or "")
    assert "ERR_USER_INPUT" in out and "story not found" in out.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_story_pending_status_raises(tmp_path: Path) -> None:
    """AC2: story status=pending → error 'story not active', exit 1."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    _write_story(tmp_path, status="pending")

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    out = r.stdout + (r.stderr or "")
    assert "ERR_USER_INPUT" in out and "story not active" in out.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_story_done_status_raises(tmp_path: Path) -> None:
    """AC2: story status=done → error 'story not active', exit 1."""
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    _write_story(tmp_path, status="done")

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    out = r.stdout + (r.stderr or "")
    assert "ERR_USER_INPUT" in out and "story not active" in out.lower()


# ---------------------------------------------------------------------------
# AC3 — Idempotency guard
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_tasks_dir_already_has_task_raises(tmp_path: Path) -> None:
    """AC3: tasks dir already has ≥1 T*.json → error 'already broken', exit 1."""
    _ready_repo(tmp_path)
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T01-something.json").write_text("{}", encoding="utf-8")

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    out = r.stdout + (r.stderr or "")
    assert "ERR_USER_INPUT" in out and "story already broken into" in out.lower()


# ---------------------------------------------------------------------------
# AC4/AC5/AC6 — Happy path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_3_tasks_written_and_journal(tmp_path: Path) -> None:
    """AC4/AC5/AC6: full happy path → 3 task files written, journal sequence correct, exit 0."""
    _ready_repo(tmp_path)
    dispatch_result = _make_dispatch_result(_three_task_batch())
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    initial_lines = (
        len(journal_path.read_text(encoding="utf-8").splitlines()) if journal_path.exists() else 0
    )

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.break_.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")

    # 3 task files written
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    task_files = sorted(tasks_dir.glob("T*-*.json"))
    assert len(task_files) == 3
    assert task_files[0].name.startswith("T01-")
    assert task_files[1].name.startswith("T02-")
    assert task_files[2].name.startswith("T03-")

    # emit_json success
    out = json.loads(r.stdout)
    assert out["outcome"] == "success"
    assert out["phase"] == 3
    assert out["track"] == "break"
    assert out["story_id"] == _STORY_ID
    assert out["task_count"] == 3
    assert len(out["task_ids"]) == 3

    # journal: agent_dispatched + 3x artifact_written + story_broken_into_tasks
    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    new_entries = entries[initial_lines:]
    kinds = [e.get("kind") for e in new_entries]
    assert "agent_dispatched" in kinds
    assert kinds.count("artifact_written") == 3
    assert kinds[-1] == "story_broken_into_tasks"


# ---------------------------------------------------------------------------
# AC5 — Mid-batch hook denial → rollback
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_mid_batch_hook_denial_rolls_back(tmp_path: Path) -> None:
    """AC5: hook denies 3rd task write → rollback first 2 already-written files, exit 1."""
    _ready_repo(tmp_path)
    dispatch_result = _make_dispatch_result(_three_task_batch())

    call_count = 0

    async def _mock_run_hook_chain(payload, *, hooks, journal_path):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        decision = unittest.mock.MagicMock()
        if call_count >= 3:
            decision.decision = "deny"
            decision.hook_name = "test-hook"
            decision.reason = "test denial"
        else:
            decision.decision = "allow"
        return decision

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch(
            "sdlc.cli._break_pipeline.run_hook_chain", side_effect=_mock_run_hook_chain
        ),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1

    # all written files must be rolled back
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    task_files = list(tasks_dir.glob("T*-*.json")) if tasks_dir.exists() else []
    assert len(task_files) == 0, f"expected rollback, but found: {[f.name for f in task_files]}"

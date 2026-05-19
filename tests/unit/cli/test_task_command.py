"""Unit tests for cli/task.py:run_task — AC1-AC3 (Story 2A.17, Task 4.1)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest

from sdlc.cli.main import app
from sdlc.dispatcher.prompts import BOUNDARY_LINE
from unit.cli._task_command_helpers import (
    _STORY_ID,
    _TASK_ID,
    _init_repo,
    _invoke_task,
    _make_dispatch_result,
    _runner,
    _setup_approved_repo,
    _task_path,
    _write_approved_signoff,
    _write_story,
    _write_task,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# AC1 — TASK-id validation
# ---------------------------------------------------------------------------


def test_invalid_task_id_exits_nonzero(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    r = _invoke_task(tmp_path, task_id="not-a-valid-task-id")
    assert r.exit_code != 0
    output = r.output
    assert "ERR_USER_INPUT" in output or "invalid TASK-id" in output


def test_story_id_as_task_id_exits_nonzero(tmp_path: Path) -> None:
    """Story IDs (no T-segment) must be rejected."""
    _setup_approved_repo(tmp_path)
    r = _invoke_task(tmp_path, task_id=_STORY_ID)
    assert r.exit_code != 0


# ---------------------------------------------------------------------------
# AC1 — Init guard
# ---------------------------------------------------------------------------


def test_not_initialized_exits_nonzero(tmp_path: Path) -> None:
    r = _invoke_task(tmp_path)
    assert r.exit_code != 0
    assert "ERR_NOT_INITIALIZED" in r.output or "not initialized" in r.output


# ---------------------------------------------------------------------------
# AC1 — Phase 2 gate
# ---------------------------------------------------------------------------


def test_phase2_not_approved_exits_nonzero(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    r = _invoke_task(tmp_path)
    assert r.exit_code != 0
    assert "ERR_PHASE2_NOT_APPROVED" in r.output or "phase 2" in r.output.lower()


def test_phase2_not_approved_no_dispatch(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch") as mock_dispatch,
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        _runner.invoke(app, ["--json", "task", _TASK_ID])
    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# AC2 — Task file lookup
# ---------------------------------------------------------------------------


def test_task_file_missing_exits_nonzero(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    r = _invoke_task(tmp_path)
    assert r.exit_code != 0
    assert "task not found" in r.output.lower() or "ERR_USER_INPUT" in r.output


def test_task_file_missing_mentions_sdlc_break(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    r = _invoke_task(tmp_path)
    assert "sdlc-break" in r.output or "sdlc break" in r.output or "break" in r.output.lower()


def test_task_already_done_exits_nonzero(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="done", review_verdict="approved")
    _write_story(tmp_path)
    r = _invoke_task(tmp_path)
    assert r.exit_code != 0
    assert "task already complete" in r.output.lower() or "done" in r.output.lower()


def test_task_already_done_no_dispatch(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="done", review_verdict="approved")
    _write_story(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch") as mock_dispatch,
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        _runner.invoke(app, ["--json", "task", _TASK_ID])
    mock_dispatch.assert_not_called()


def test_task_json_with_boundary_line_exits_nonzero(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    p = _task_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# task\n{BOUNDARY_LINE}\n", encoding="utf-8")
    r = _invoke_task(tmp_path)
    assert r.exit_code != 0
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in r.output or "boundary" in r.output.lower()


# ---------------------------------------------------------------------------
# AC3 — pending → write-tests (test-author)
# ---------------------------------------------------------------------------


def test_pending_to_write_tests_dispatches_test_author(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="pending")
    _write_story(tmp_path)

    test_files_output = json.dumps(
        {
            "files": [{"path": "tests/unit/test_foo.py", "content": "# test"}],
            "tests_status": "red",
        }
    )
    dispatch_result = _make_dispatch_result(test_files_output)

    with (
        unittest.mock.patch(
            "sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result
        ) as mock_dispatch,
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    mock_dispatch.assert_called_once()
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "write-tests"


def test_pending_to_write_tests_writes_test_file(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="pending")
    _write_story(tmp_path)

    test_files_output = json.dumps(
        {
            "files": [{"path": "tests/unit/test_foo.py", "content": "# test\n"}],
            "tests_status": "red",
        }
    )
    dispatch_result = _make_dispatch_result(test_files_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert (tmp_path / "tests" / "unit" / "test_foo.py").exists()


def test_pending_to_write_tests_journals_task_stage_advanced(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="pending")
    _write_story(tmp_path)

    test_files_output = json.dumps(
        {
            "files": [{"path": "tests/unit/test_foo.py", "content": "# test"}],
            "tests_status": "red",
        }
    )
    dispatch_result = _make_dispatch_result(test_files_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "task_stage_advanced" in journal


def test_test_author_writes_outside_tests_exits_nonzero(tmp_path: Path) -> None:
    """test-author must only write under tests/ (AC3)."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="pending")
    _write_story(tmp_path)

    bad_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/foo.py", "content": "# nope"}],
            "tests_status": "red",
        }
    )
    dispatch_result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    assert "test-author wrote outside tests/" in r.output or "outside" in r.output.lower()

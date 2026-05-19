"""Unit tests for cli/task.py:run_task — AC4-AC10 (Story 2A.17, Task 4.1)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest

from sdlc.cli.main import app
from unit.cli._task_command_helpers import (
    _TASK_ID,
    _invoke_task,
    _make_dispatch_result,
    _runner,
    _setup_approved_repo,
    _task_path,
    _write_story,
    _write_task,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# AC4 — write-tests → write-code (code-author)
# ---------------------------------------------------------------------------


def test_write_tests_to_write_code_dispatches_code_author(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="write-tests")
    _write_story(tmp_path)

    code_files_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/foo.py", "content": "x = 1"}],
            "tests_status": "green",
        }
    )
    dispatch_result = _make_dispatch_result(code_files_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "write-code"
    assert (tmp_path / "src" / "sdlc" / "foo.py").exists()


def test_code_author_reports_red_exits_nonzero_and_rolls_back(tmp_path: Path) -> None:
    """RED→GREEN gate: code-author still reporting red → failure + rollback (AC4/AC7)."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="write-tests")
    _write_story(tmp_path)

    code_files_output = json.dumps(
        {
            "files": [{"path": "src/sdlc/foo.py", "content": "x = 1"}],
            "tests_status": "red",
        }
    )
    dispatch_result = _make_dispatch_result(code_files_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "write-tests"
    assert not (tmp_path / "src" / "sdlc" / "foo.py").exists()
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "task_stage_failed" in journal


def test_code_author_writes_outside_src_exits_nonzero(tmp_path: Path) -> None:
    """code-author must only write under src/ (AC4)."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="write-tests")
    _write_story(tmp_path)

    bad_output = json.dumps(
        {
            "files": [{"path": "tests/unit/test_foo.py", "content": "# nope"}],
            "tests_status": "green",
        }
    )
    dispatch_result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    assert "code-author wrote outside src/" in r.output or "outside" in r.output.lower()


# ---------------------------------------------------------------------------
# AC5 — write-code → review (code-reviewer, verdict captured)
# ---------------------------------------------------------------------------


def test_write_code_to_review_captures_verdict(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="write-code")
    _write_story(tmp_path)

    review_output = json.dumps({"verdict": "approved", "notes": "LGTM"})
    dispatch_result = _make_dispatch_result(review_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "review"
    assert task_data["review_verdict"] == "approved"
    assert task_data["review_notes"] == "LGTM"


def test_write_code_to_review_rejected_verdict_still_advances_stage(tmp_path: Path) -> None:
    """Even rejected verdict advances to review (AC5 — review means 'a review happened')."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="write-code")
    _write_story(tmp_path)

    review_output = json.dumps({"verdict": "rejected", "notes": "needs work"})
    dispatch_result = _make_dispatch_result(review_output)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "review"
    assert task_data["review_verdict"] == "rejected"


# ---------------------------------------------------------------------------
# AC6 — review → done (clean-verdict gate, no dispatch)
# ---------------------------------------------------------------------------


def test_review_to_done_with_approved_succeeds_no_dispatch(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="review", review_verdict="approved", review_notes="LGTM")
    _write_story(tmp_path)

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch") as mock_dispatch,
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code == 0, r.output
    mock_dispatch.assert_not_called()
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "done"


def test_review_to_done_with_rejected_exits_nonzero(tmp_path: Path) -> None:
    """Rejected review at review→done transition must fail (AC6/AC7)."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="review", review_verdict="rejected", review_notes="nope")
    _write_story(tmp_path)

    with unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "review"
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "task_stage_failed" in journal
    assert "review rejected" in r.output.lower() or "rejected" in r.output.lower()


# ---------------------------------------------------------------------------
# AC7 — mid-write hook denial → rollback
# ---------------------------------------------------------------------------


def test_hook_denial_rolls_back_and_journals_stage_failed(tmp_path: Path) -> None:
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

    deny_decision = unittest.mock.MagicMock()
    deny_decision.decision = "deny"
    deny_decision.hook_name = "test-hook"
    deny_decision.reason = "blocked by hook"

    with (
        unittest.mock.patch("sdlc.cli._task_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli._task_pipeline.run_hook_chain", return_value=deny_decision),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        r = _runner.invoke(app, ["--json", "task", _TASK_ID])

    assert r.exit_code != 0
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "pending"
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "task_stage_failed" in journal


# ---------------------------------------------------------------------------
# AC10 — success envelope
# ---------------------------------------------------------------------------


def test_success_envelope_shape(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, stage="review", review_verdict="approved", review_notes="OK")
    _write_story(tmp_path)

    r = _invoke_task(tmp_path)

    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["phase"] == 3
    assert data["track"] == "task"
    assert data["task_id"] == _TASK_ID
    assert data["from"] == "review"
    assert data["to"] == "done"
    assert data["outcome"] == "success"

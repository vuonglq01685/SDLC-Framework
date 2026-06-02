"""Story 3.8 — `/sdlc-task` dispatches the characterization-test author for legacy tasks (AC3/AC4).

For a `pending` task whose `tdd_strategy == characterization-test`, the pipeline selects
`characterization-author` (not `test-author`) and the RED-gate accepts `green` (characterization
tests capture current behavior and are expected to pass). `write-tests-first` tasks are unchanged:
`test-author` at `pending` with the strict RED-gate.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from unit.cli._task_command_helpers import (
    _STORY_ID,
    _TASK_ID,
    _setup_approved_repo,
    _task_path,
    _write_story,
)

pytestmark = [pytest.mark.unit, pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")]

_runner = CliRunner()


def _write_task(tmp_path: Path, *, tdd_strategy: str, stage: str = "pending") -> Path:
    p = _task_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "id": _TASK_ID,
        "story_id": _STORY_ID,
        "label": "Refactor the legacy core.",
        "stage": stage,
        "dependencies": [],
        "review_verdict": None,
        "review_notes": None,
        "tdd_strategy": tdd_strategy,
    }
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _green_tests_payload() -> str:
    return json.dumps(
        {
            "files": [
                {"path": "tests/unit/test_legacy_core.py", "content": "# characterization\n"}
            ],
            "tests_status": "green",
        }
    )


def _red_tests_payload() -> str:
    return json.dumps(
        {
            "files": [{"path": "tests/unit/test_legacy_core.py", "content": "# red\n"}],
            "tests_status": "red",
        }
    )


def _invoke(tmp_path: Path, output_text: str) -> object:
    with (
        unittest.mock.patch(
            "sdlc.cli._task_pipeline.dispatch", return_value=_dispatch_result(output_text)
        ),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        return _runner.invoke(app, ["--json", "task", _TASK_ID])


# ---------------------------------------------------------------------------
# AC3/AC4 — characterization task: characterization-author + green accepted.
# ---------------------------------------------------------------------------


def test_characterization_task_advances_on_green(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, tdd_strategy="characterization-test")
    _write_story(tmp_path)

    r = _invoke(tmp_path, _green_tests_payload())

    assert r.exit_code == 0, r.output
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "write-tests"
    assert (tmp_path / "tests" / "unit" / "test_legacy_core.py").exists()


def test_characterization_dispatch_journals_characterization_author(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, tdd_strategy="characterization-test")
    _write_story(tmp_path)

    r = _invoke(tmp_path, _green_tests_payload())

    assert r.exit_code == 0, r.output
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "characterization-author" in journal
    # success envelope names the characterization author
    assert json.loads(r.output)["specialist"] == "characterization-author"


def test_characterization_task_red_status_is_rejected(tmp_path: Path) -> None:
    """Characterization tests must PASS against current behavior — a red report fails the gate."""
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, tdd_strategy="characterization-test")
    _write_story(tmp_path)

    r = _invoke(tmp_path, _red_tests_payload())

    assert r.exit_code != 0
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "pending"
    assert not (tmp_path / "tests" / "unit" / "test_legacy_core.py").exists()


# ---------------------------------------------------------------------------
# Greenfield regression — write-tests-first task unchanged (test-author, RED-gate).
# ---------------------------------------------------------------------------


def test_write_tests_first_task_uses_test_author_and_requires_red(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, tdd_strategy="write-tests-first")
    _write_story(tmp_path)

    # green at the pending stage must FAIL for the strict TDD path (unchanged behavior).
    r = _invoke(tmp_path, _green_tests_payload())

    assert r.exit_code != 0
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "pending"


def test_write_tests_first_task_advances_on_red(tmp_path: Path) -> None:
    _setup_approved_repo(tmp_path)
    _write_task(tmp_path, tdd_strategy="write-tests-first")
    _write_story(tmp_path)

    r = _invoke(tmp_path, _red_tests_payload())

    assert r.exit_code == 0, r.output
    task_data = json.loads(_task_path(tmp_path).read_text())
    assert task_data["stage"] == "write-tests"
    journal = (tmp_path / ".claude" / "state" / "journal.log").read_text()
    assert "test-author" in journal

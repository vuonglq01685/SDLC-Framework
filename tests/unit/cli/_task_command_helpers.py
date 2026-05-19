"""Shared helpers for test_task_command* unit tests (Story 2A.17)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app

_STORY_ID = "EPIC-foo-S01-bar"
_EPIC_ID = "EPIC-foo"
_TASK_ID = "EPIC-foo-S01-bar-T01-design-data-model"

_runner = CliRunner()


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


def _task_json(
    *, stage: str = "pending", review_verdict: str | None = None, review_notes: str | None = None
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


def _story_json() -> str:
    data = {
        "schema_version": 1,
        "id": _STORY_ID,
        "epic_id": _EPIC_ID,
        "seq": 1,
        "label": "Design system",
        "as_a": "developer",
        "i_want": "a system",
        "so_that": "it works",
        "given_when_then": ["Given a system, when run, then works."],
        "dependencies": [],
        "drafted_at": "2026-05-18T10:00:00Z",
        "drafted_by_specialist": "test",
    }
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _task_path(tmp_path: Path) -> Path:
    return tmp_path / "03-Implementation" / "tasks" / _STORY_ID / "T01-design-data-model.json"


def _story_path(tmp_path: Path) -> Path:
    return tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID / f"{_STORY_ID}.json"


def _write_task(
    tmp_path: Path,
    *,
    stage: str = "pending",
    review_verdict: str | None = None,
    review_notes: str | None = None,
) -> Path:
    p = _task_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        _task_json(stage=stage, review_verdict=review_verdict, review_notes=review_notes),
        encoding="utf-8",
    )
    return p


def _write_story(tmp_path: Path) -> Path:
    p = _story_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_story_json(), encoding="utf-8")
    return p


def _setup_approved_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, phase=1)
    _write_approved_signoff(tmp_path, phase=2)


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _invoke_task(tmp_path: Path, task_id: str = _TASK_ID, *, json_mode: bool = True) -> object:
    args = ["--json", "task", task_id] if json_mode else ["task", task_id]
    with unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)

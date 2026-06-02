"""Story 3.8 — `/sdlc-break` reads `legacy_code_globs` and stamps `tdd_strategy` (AC1/AC7/D2).

The classifier is deterministic and CLI-side: each emitted task carries a `touches` array; tasks
whose touched paths match `legacy_code_globs` get `tdd_strategy: characterization-test`, all others
`write-tests-first`. Greenfield (no/empty globs) keeps every task `write-tests-first` (regression).
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = [pytest.mark.unit, pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")]

_runner = CliRunner()

_STORY_ID = "EPIC-foo-S01-bar"
_EPIC_ID = "EPIC-foo"
_PRODUCT_CONTENT = "# Product Brief\n\n## Overview\n\nA product for testing.\n"

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
    "status": "in-progress",
}


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
            {"schema_version": 1, "path": f"0{phase}-a/a.md", "hash": "sha256:" + "a" * 64}
        ],
        "approved_by": "test-approver",
        "approved_at": "2026-05-17T10:00:00.000Z",
        "drafted_at": "2026-05-17T09:00:00.000Z",
        "validated_at": "2026-05-17T10:00:00.000Z",
    }
    (signoffs_dir / f"phase-{phase}.yaml").write_text(
        yaml.safe_dump(record, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )


def _ready_repo(tmp_path: Path, *, legacy_code_globs: list[str] | None = None) -> None:
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Requirement" / "01-PRODUCT.md").write_text(_PRODUCT_CONTENT, encoding="utf-8")
    story_path = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID / f"{_STORY_ID}.json"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(json.dumps(_BASE_STORY, sort_keys=True, indent=2), encoding="utf-8")
    if legacy_code_globs is not None:
        (tmp_path / "project.yaml").write_text(
            yaml.safe_dump({"legacy_code_globs": legacy_code_globs}, sort_keys=True),
            encoding="utf-8",
        )


def _task_batch_with_touches() -> str:
    """T01 touches a legacy path; T02/T03 touch non-legacy paths."""
    return json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-refactor-legacy-core",
                "story_id": _STORY_ID,
                "label": "Refactor the legacy core module.",
                "stage": "pending",
                "dependencies": [],
                "touches": ["src/legacy/core.py"],
            },
            {
                "id": f"{_STORY_ID}-T02-add-new-service",
                "story_id": _STORY_ID,
                "label": "Add a brand-new service.",
                "stage": "pending",
                "dependencies": [],
                "touches": ["src/app/service.py"],
            },
            {
                "id": f"{_STORY_ID}-T03-wire-service",
                "story_id": _STORY_ID,
                "label": "Wire the new service into the app.",
                "stage": "pending",
                "dependencies": [f"{_STORY_ID}-T02-add-new-service"],
                "touches": ["src/app/wiring.py"],
            },
        ],
        ensure_ascii=False,
    )


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _run_break(tmp_path: Path) -> object:
    dispatch_result = _make_dispatch_result(_task_batch_with_touches())
    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.break_.evaluate_postconditions"),
    ):
        return _runner.invoke(app, ["--json", "break", _STORY_ID])


def _read_tasks(tmp_path: Path) -> dict[str, dict]:
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    out: dict[str, dict] = {}
    for f in sorted(tasks_dir.glob("T*-*.json")):
        out[f.name] = json.loads(f.read_text(encoding="utf-8"))
    return out


# ---------------------------------------------------------------------------
# AC1/AC7 — brownfield: legacy-touching task → characterization-test.
# ---------------------------------------------------------------------------


def test_legacy_touch_gets_characterization_test(tmp_path: Path) -> None:
    _ready_repo(tmp_path, legacy_code_globs=["src/legacy/**"])
    r = _run_break(tmp_path)
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    tasks = _read_tasks(tmp_path)
    t01 = next(v for k, v in tasks.items() if k.startswith("T01-"))
    assert t01["tdd_strategy"] == "characterization-test"


def test_non_legacy_tasks_stay_write_tests_first(tmp_path: Path) -> None:
    _ready_repo(tmp_path, legacy_code_globs=["src/legacy/**"])
    r = _run_break(tmp_path)
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    tasks = _read_tasks(tmp_path)
    t02 = next(v for k, v in tasks.items() if k.startswith("T02-"))
    t03 = next(v for k, v in tasks.items() if k.startswith("T03-"))
    assert t02["tdd_strategy"] == "write-tests-first"
    assert t03["tdd_strategy"] == "write-tests-first"


def test_touches_not_persisted_in_task_files(tmp_path: Path) -> None:
    _ready_repo(tmp_path, legacy_code_globs=["src/legacy/**"])
    r = _run_break(tmp_path)
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    for data in _read_tasks(tmp_path).values():
        assert "touches" not in data


# ---------------------------------------------------------------------------
# AC7 — greenfield regression: no/empty globs → all write-tests-first.
# ---------------------------------------------------------------------------


def test_greenfield_no_project_yaml_all_write_tests_first(tmp_path: Path) -> None:
    _ready_repo(tmp_path, legacy_code_globs=None)  # no project.yaml at all
    r = _run_break(tmp_path)
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    for data in _read_tasks(tmp_path).values():
        assert data["tdd_strategy"] == "write-tests-first"


def test_greenfield_empty_globs_all_write_tests_first(tmp_path: Path) -> None:
    _ready_repo(tmp_path, legacy_code_globs=[])
    r = _run_break(tmp_path)
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    for data in _read_tasks(tmp_path).values():
        assert data["tdd_strategy"] == "write-tests-first"

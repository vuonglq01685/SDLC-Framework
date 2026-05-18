"""Unit tests for ``sdlc break`` CLI response to invalid specialist output (Story 2A.16, AC4, AC8).

Tests the full CLI path (mocked dispatch) when the specialist returns
bad task batches (wrong story_id, duplicates, orphan deps, dep cycles,
seq gaps) and when PRODUCT.md / story JSON contains the boundary line.
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

pytestmark = pytest.mark.unit

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
}


def _story_json(*, status: str = "in-progress") -> str:
    data = dict(_BASE_STORY)
    data["status"] = status
    return json.dumps(data, sort_keys=True, indent=2)


def _story_path(tmp_path: Path) -> Path:
    return tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID / f"{_STORY_ID}.json"


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
    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    _write_story(tmp_path, status="in-progress")


def _three_task_batch(story_id: str = _STORY_ID) -> str:
    from sdlc.cli._break_pipeline import mock_task_batch_body

    return mock_task_batch_body(story_id)


# ---------------------------------------------------------------------------
# AC4 — Specialist output validation (via CLI with mocked dispatch)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_wrong_story_id_in_task_raises(tmp_path: Path) -> None:
    """AC4: task declares wrong story_id → WorkflowError 'wrong story_id', exit 1."""
    _ready_repo(tmp_path)
    bad_output = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": "EPIC-other-S01-story",
                "label": "wrong story",
                "stage": "pending",
                "dependencies": [],
            }
        ]
    )
    result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=result),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "wrong story_id" in (r.stdout + (r.stderr or "")).lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_duplicate_task_ids_raises(tmp_path: Path) -> None:
    """AC4: duplicate task id → WorkflowError 'duplicate task id', exit 1."""
    _ready_repo(tmp_path)
    bad_output = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": _STORY_ID,
                "label": "x",
                "stage": "pending",
                "dependencies": [],
            },
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": _STORY_ID,
                "label": "y",
                "stage": "pending",
                "dependencies": [],
            },
        ]
    )
    result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=result),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "duplicate task id" in (r.stdout + (r.stderr or "")).lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_orphan_dependency_raises(tmp_path: Path) -> None:
    """AC4: task dep not in batch → WorkflowError 'dependency not in this batch', exit 1."""
    _ready_repo(tmp_path)
    bad_output = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": _STORY_ID,
                "label": "x",
                "stage": "pending",
                "dependencies": [f"{_STORY_ID}-T99-nonexistent"],
            }
        ]
    )
    result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=result),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "not in this batch" in (r.stdout + (r.stderr or "")).lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_dep_cycle_raises(tmp_path: Path) -> None:
    """AC4: T01→T02→T01 cycle → WorkflowError 'cycle', exit 1."""
    _ready_repo(tmp_path)
    bad_output = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": _STORY_ID,
                "label": "x",
                "stage": "pending",
                "dependencies": [f"{_STORY_ID}-T02-bar"],
            },
            {
                "id": f"{_STORY_ID}-T02-bar",
                "story_id": _STORY_ID,
                "label": "y",
                "stage": "pending",
                "dependencies": [f"{_STORY_ID}-T01-foo"],
            },
        ]
    )
    result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=result),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "cycle" in (r.stdout + (r.stderr or "")).lower()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_seq_gap_raises(tmp_path: Path) -> None:
    """AC5: T01 + T03 (skip T02) → WorkflowError 'seq gap', exit 1."""
    _ready_repo(tmp_path)
    bad_output = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-foo",
                "story_id": _STORY_ID,
                "label": "x",
                "stage": "pending",
                "dependencies": [],
            },
            {
                "id": f"{_STORY_ID}-T03-baz",
                "story_id": _STORY_ID,
                "label": "z",
                "stage": "pending",
                "dependencies": [],
            },
        ]
    )
    result = _make_dispatch_result(bad_output)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=result),
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 1
    assert "seq gap" in (r.stdout + (r.stderr or "")).lower()


# ---------------------------------------------------------------------------
# AC8 — Compound prompt secondary_input = story JSON text
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_compound_prompt_secondary_input_is_story_json(tmp_path: Path) -> None:
    """AC8: phase1_compound_prompt_builder called with secondary_input=raw story JSON text."""
    _ready_repo(tmp_path)
    expected_story_text = (_story_path(tmp_path)).read_text(encoding="utf-8")
    dispatch_result = _make_dispatch_result(_three_task_batch())

    from sdlc.dispatcher import phase1_compound_prompt_builder as _real_builder

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch("sdlc.cli.break_.evaluate_postconditions"),
        unittest.mock.patch(
            "sdlc.cli.break_.phase1_compound_prompt_builder",
            wraps=_real_builder,
        ) as mock_builder,
    ):
        r = _runner.invoke(app, ["--json", "break", _STORY_ID])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert mock_builder.called
    _, call_kwargs = mock_builder.call_args
    assert call_kwargs.get("secondary_input") == expected_story_text


# ---------------------------------------------------------------------------
# AC8 — BOUNDARY_LINE pollution
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_boundary_in_product_md_raises(tmp_path: Path) -> None:
    """AC8: PRODUCT.md contains boundary line → ERR_ARTIFACT_CONTAINS_BOUNDARY, exit 1."""
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path, content=f"# Product\n\n{BOUNDARY_LINE}\n\nContent\n")
    _write_story(tmp_path, status="in-progress")

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_boundary_in_story_json_raises(tmp_path: Path) -> None:
    """AC8: story JSON contains boundary line → ERR_ARTIFACT_CONTAINS_BOUNDARY, exit 1."""
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _init_repo(tmp_path)
    _write_approved_signoff(tmp_path, 1)
    _write_approved_signoff(tmp_path, 2)
    _write_product_md(tmp_path)
    _write_story(tmp_path, raw=f"{_story_json()}\n\n{BOUNDARY_LINE}\n")

    r = _invoke_break(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + (r.stderr or ""))

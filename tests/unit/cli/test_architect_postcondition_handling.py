"""Unit tests for cli/architect.py postcondition + idempotency handling.

Split out of ``test_architect_command.py`` (code review CR14-P13/D2) to keep
that module under the 400-line cap. Covers the ``run_architect`` →
``evaluate_postconditions`` error-mapping branches — previously unit-untested
because every happy-path test mocked the call away — and the orphan
sub-track-file cleanup on re-run (CR14-D2).
"""

from __future__ import annotations

import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()

_ARCH_CONTENT_NO_REQUIRES = "## Overview\n\nSystem architecture stub.\n"


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_product_md(tmp_path: Path) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Product Brief\n\nA product for testing.\n", encoding="utf-8")
    return p


def _write_approved_phase1_signoff(tmp_path: Path) -> None:
    """Write a canonical phase-1 signoff record so compute_state returns APPROVED."""
    signoffs_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "phase": 1,
        "artifacts": [
            {
                "schema_version": 1,
                "path": "01-Requirement/01-PRODUCT.md",
                "hash": "sha256:" + "a" * 64,
            }
        ],
        "approved_by": "test-approver",
        "approved_at": "2026-05-14T10:00:00.000Z",
        "drafted_at": "2026-05-14T09:00:00.000Z",
        "validated_at": "2026-05-14T10:00:00.000Z",
    }
    (signoffs_dir / "phase-1.yaml").write_text(
        yaml.safe_dump(record, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def _make_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_postcondition_workflow_error_maps_to_error_code(tmp_path: Path) -> None:
    """AC8: a postcondition WorkflowError surfaces as ERR_POSTCONDITION_FAILED."""
    from sdlc.errors import WorkflowError

    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_NO_REQUIRES)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
        unittest.mock.patch(
            "sdlc.cli.architect.evaluate_postconditions",
            side_effect=WorkflowError("postcondition architecture_md_written: file is empty"),
        ),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 1
    assert "ERR_POSTCONDITION_FAILED" in (r.stdout + (r.stderr or ""))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_postcondition_runtime_error_maps_to_wiring_incomplete(tmp_path: Path) -> None:
    """AC8: a RuntimeError (caller forgot to plumb a path) maps to ERR_POSTCONDITION_FAILED."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    primary_result = _make_dispatch_result(_ARCH_CONTENT_NO_REQUIRES)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
        unittest.mock.patch(
            "sdlc.cli.architect.evaluate_postconditions",
            side_effect=RuntimeError("postcondition architecture_md_written requires ..."),
        ),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 1
    output = r.stdout + (r.stderr or "")
    assert "ERR_POSTCONDITION_FAILED" in output
    assert "wiring incomplete" in output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_orphan_sub_track_files_removed_on_rerun(tmp_path: Path) -> None:
    """CR14-D2: a stale sub-tracks/*.md from a prior run is removed when no longer required."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    # Seed an orphan from a hypothetical prior run with a larger requires: set.
    sub_dir = tmp_path / "02-Architecture" / "02-System" / "sub-tracks"
    sub_dir.mkdir(parents=True, exist_ok=True)
    orphan = sub_dir / "security.md"
    orphan.write_text("## Stale Security\n\nLeftover.\n", encoding="utf-8")

    primary_result = _make_dispatch_result(_ARCH_CONTENT_NO_REQUIRES)

    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._architect_pipeline.dispatch", return_value=primary_result),
        unittest.mock.patch("sdlc.cli.architect.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "architect"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert not orphan.exists(), "orphan sub-track file must be removed when not in requires:"

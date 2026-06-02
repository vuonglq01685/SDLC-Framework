"""Unit tests for cli/ux.py:run_ux (AC1, AC5, AC6, AC7 — Story 2A.13)."""

from __future__ import annotations

import json
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

# Two-file JSON response from ux-designer
_MOCK_UX_RESPONSE = json.dumps(
    [
        {"filename": "01-tokens.md", "content": "# Design Tokens\n\n...stub..."},
        {"filename": "02-flows.md", "content": "# User Flows\n\n...stub..."},
    ]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_product_md(tmp_path: Path, content: str | None = None) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = "# Product Brief\n\nA product for testing.\n"
    p.write_text(content, encoding="utf-8")
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


def _make_mock_dispatch_result(output_text: str) -> unittest.mock.MagicMock:
    result = unittest.mock.MagicMock()
    result.outcome = "success"
    result.agent_result.output_text = output_text
    return result


def _invoke_ux(tmp_path: Path, *, json_mode: bool = True) -> object:
    args = ["--json", "ux"] if json_mode else ["ux"]
    with unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Pre-flight: not initialized
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_not_initialized(tmp_path: Path) -> None:
    """AC1: ERR_NOT_INITIALIZED if state.json missing."""
    with unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "ux"])
    assert r.exit_code == 1
    assert "ERR_NOT_INITIALIZED" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Pre-flight: Phase 1 not APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_phase1_not_approved(tmp_path: Path) -> None:
    """AC1: ERR_PHASE1_NOT_APPROVED when phase 1 is AWAITING_SIGNOFF."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF
    r = _invoke_ux(tmp_path)
    assert r.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_phase1_not_approved_no_dispatch_called(tmp_path: Path) -> None:
    """AC1 defense-in-depth: no dispatch call when phase 1 gate fires."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch") as mock_dispatch,
    ):
        r = _runner.invoke(app, ["--json", "ux"])
    assert r.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (r.stdout + r.stderr)
    mock_dispatch.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_phase1_signoff_corrupt(tmp_path: Path) -> None:
    """P2 / DB1=c (review-B): malformed signoff YAML → ERR_SIGNOFF_READ_FAILED (exit 2).

    Distinguishes corrupt-read from not-approved (which is ERR_PHASE1_NOT_APPROVED).
    """
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    signoffs_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    # Malformed YAML (unterminated quote) so compute_state raises SignoffError.
    (signoffs_dir / "phase-1.yaml").write_text('phase: "', encoding="utf-8")
    with unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "ux"])
    assert r.exit_code == 2, r.stdout + (r.stderr or "")
    assert "ERR_SIGNOFF_READ_FAILED" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_rejects_reserved_anchor_filename(tmp_path: Path) -> None:
    """P1 (review-A): specialist returning ``00-*.md`` collides with phantom anchor → rejected."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)
    mock_result = _make_mock_dispatch_result(
        json.dumps([{"filename": "00-ux-dispatch-anchor.md", "content": "x"}])
    )
    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
    ):
        r = _runner.invoke(app, ["--json", "ux"])
    assert r.exit_code == 1
    assert "ERR_UNSAFE_FILENAME" in (r.stdout + r.stderr)
    assert "reserved-anchor-prefix" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_rejects_duplicate_filename_case_insensitive(tmp_path: Path) -> None:
    """P4 + PB8 (review-B): case-insensitive duplicate-filename guard."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)
    mock_result = _make_mock_dispatch_result(
        json.dumps(
            [
                {"filename": "01-Tokens.md", "content": "first"},
                {"filename": "01-tokens.md", "content": "second-clobbers"},
            ]
        )
    )
    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
    ):
        r = _runner.invoke(app, ["--json", "ux"])
    assert r.exit_code == 1
    assert "duplicate filename" in (r.stdout + r.stderr).lower()


# ---------------------------------------------------------------------------
# Pre-flight: PRODUCT.md contains boundary marker
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_refuses_when_product_md_contains_boundary(tmp_path: Path) -> None:
    """AC5: ERR_ARTIFACT_CONTAINS_BOUNDARY if 01-PRODUCT.md has boundary marker."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _write_product_md(tmp_path, content=f"# Product\n\n{BOUNDARY_LINE}\n\nContent\n")
    r = _invoke_ux(tmp_path)
    assert r.exit_code == 1
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_writes_two_files(tmp_path: Path) -> None:
    """AC5: phase-1 APPROVED + mocked 2-file dispatch → 2 files written, exit 0."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(_MOCK_UX_RESPONSE)

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._ux_pipeline.dispatch", return_value=mock_result
        ) as mock_disp,
        # EPIC-2A-D4: dispatch mocked → mock postcondition gate (enforced elsewhere).
        unittest.mock.patch("sdlc.cli.ux.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    mock_disp.assert_called_once()

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    assert (ux_dir / "01-tokens.md").is_file()
    assert (ux_dir / "02-flows.md").is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_emit_json_success(tmp_path: Path) -> None:
    """AC1: emit_json on success has phase=2, track='ux', outcome='success', 2 artifacts."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(_MOCK_UX_RESPONSE)

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
        unittest.mock.patch("sdlc.cli.ux.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    out = json.loads(r.stdout)
    assert out["phase"] == 2
    assert out["track"] == "ux"
    assert out["specialist"] == "ux-designer"
    assert out["outcome"] == "success"
    assert len(out["artifacts"]) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_journal_entries(tmp_path: Path) -> None:
    """AC6: journal has 1 agent_dispatched + 2 artifact_written entries."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(_MOCK_UX_RESPONSE)

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
        unittest.mock.patch("sdlc.cli.ux.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    assert journal_path.is_file()
    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    assert len(dispatched) == 1, f"Expected 1 agent_dispatched, got {len(dispatched)}"
    assert dispatched[0]["payload"]["specialist"] == "ux-designer"
    assert len(written) == 2, f"Expected 2 artifact_written, got {len(written)}"
    for e in written:
        assert e["actor"] == "cli"
        assert e["before_hash"] is None
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 2
        assert e["payload"]["specialist"] == "ux-designer"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_happy_path_ux_dir_created_before_dispatch(tmp_path: Path) -> None:
    """AC7: 02-Architecture/01-UX/ created before dispatch is called."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    assert not ux_dir.exists()

    dir_existed_at_dispatch: list[bool] = []

    async def _mock_dispatch(*args: object, **kwargs: object) -> object:
        dir_existed_at_dispatch.append(ux_dir.exists())
        return _make_mock_dispatch_result(_MOCK_UX_RESPONSE)

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", side_effect=_mock_dispatch),
        unittest.mock.patch("sdlc.cli.ux.evaluate_postconditions"),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert dir_existed_at_dispatch == [True], "UX dir must exist before dispatch"


# ---------------------------------------------------------------------------
# Edge cases: unsafe filenames in response
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_rejects_path_traversal_filename(tmp_path: Path) -> None:
    """AC5: filename with path traversal (../evil.md) is rejected."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(
        json.dumps([{"filename": "../evil.md", "content": "evil"}])
    )

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 1
    assert "ERR" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_rejects_non_md_filename(tmp_path: Path) -> None:
    """AC5: filename not ending in .md is rejected."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(
        json.dumps([{"filename": "01-tokens.txt", "content": "tokens"}])
    )

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 1
    assert "ERR" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_rejects_empty_dispatch_response(tmp_path: Path) -> None:
    """AC8/AC5: empty JSON array → ERR_POSTCONDITION_FAILED (ux_dir_non_empty)."""
    _init_repo(tmp_path)
    _write_approved_phase1_signoff(tmp_path)
    _write_product_md(tmp_path)

    mock_result = _make_mock_dispatch_result(json.dumps([]))

    with (
        unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._ux_pipeline.dispatch", return_value=mock_result),
    ):
        r = _runner.invoke(app, ["--json", "ux"])

    assert r.exit_code == 1
    assert "ERR_POSTCONDITION_FAILED" in (r.stdout + r.stderr)

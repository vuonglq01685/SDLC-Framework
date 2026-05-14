"""Integration tests for ``sdlc ux`` (Story 2A.13, AC1-AC7)."""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.integration

_runner = CliRunner()

_TS1 = "2026-05-14T09:00:00.000Z"
_TS2 = "2026-05-14T10:00:00.000Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _write_product_md(tmp_path: Path) -> Path:
    req_dir = tmp_path / "01-Requirement"
    req_dir.mkdir(parents=True, exist_ok=True)
    p = req_dir / "01-PRODUCT.md"
    p.write_text("# Product Brief\n\nA product for integration testing.\n", encoding="utf-8")
    return p


def _approve_phase1(tmp_path: Path, product_path: Path) -> None:
    """Write a canonical approved SignoffRecord via write_record (real API)."""
    artifact_hash = compute_artifact_hash(product_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=artifact_hash),),
        approved_by="integration-test",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _invoke_ux(tmp_path: Path, *, json_mode: bool = True) -> object:
    args = ["--json", "ux"] if json_mode else ["ux"]
    with unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _read_journal(tmp_path: Path) -> list[dict[str, object]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# Happy path: full MockAIRuntime pipeline (no dispatch mock)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_ux_integration_full_pipeline(tmp_path: Path) -> None:
    """AC1/AC5/AC6/AC7: full pipeline with MockAIRuntime — 3 placeholder files written."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_ux(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: UX directory created with .md files
    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    assert ux_dir.is_dir()
    md_files = sorted(ux_dir.glob("*.md"))
    assert len(md_files) >= 1, f"Expected ≥1 .md files, got: {[f.name for f in md_files]}"

    # AC9 anti-tautology: file content is non-trivial (not empty placeholder)
    for f in md_files:
        content = f.read_text(encoding="utf-8")
        assert len(content) > 5, f"{f.name} has trivial content"
        assert content.strip().startswith("#"), f"{f.name} must start with a markdown heading"

    # AC6: journal has agent_dispatched + artifact_written entries
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    assert len(dispatched) >= 1, "journal must have at least 1 agent_dispatched entry"
    assert dispatched[0]["payload"]["specialist"] == "ux-designer"
    assert len(written) >= 1, "journal must have at least 1 artifact_written entry"
    for e in written:
        assert e["actor"] == "cli"
        assert e["before_hash"] is None
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 2
        assert e["payload"]["specialist"] == "ux-designer"

    # AC1: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 2
    assert out["track"] == "ux"
    assert out["specialist"] == "ux-designer"
    assert out["outcome"] == "success"
    assert isinstance(out["artifacts"], list)
    assert len(out["artifacts"]) >= 1
    for artifact in out["artifacts"]:
        assert "path" in artifact
        assert "hash" in artifact
        assert artifact["hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# Phase 1 gate: phase 1 not approved → ERR_PHASE1_NOT_APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_ux_integration_requires_phase1_approved(tmp_path: Path) -> None:
    """AC1: sdlc ux refuses with ERR_PHASE1_NOT_APPROVED when phase 1 not approved."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF

    result = _invoke_ux(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (result.stdout + (result.stderr or ""))

    # No UX files must be written
    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    if ux_dir.exists():
        assert list(ux_dir.glob("*.md")) == []

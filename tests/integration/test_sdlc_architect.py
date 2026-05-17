"""Integration tests for ``sdlc architect`` (Story 2A.14, AC1-AC8)."""

from __future__ import annotations

import functools
import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli import _architect_pipeline as _ap
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


def _invoke_architect(tmp_path: Path, *, json_mode: bool = True) -> object:
    args = ["--json", "architect"] if json_mode else ["architect"]
    with unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path):
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
def test_sdlc_architect_integration_full_pipeline(tmp_path: Path) -> None:
    """AC2/AC3/AC5/AC8: full pipeline — ARCHITECTURE.md + sub-track files written."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_architect(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: ARCHITECTURE.md created under 02-Architecture/02-System/
    arch_path = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_path.is_file(), "ARCHITECTURE.md must be written"
    arch_text = arch_path.read_text(encoding="utf-8")
    assert len(arch_text.strip()) > 5, "ARCHITECTURE.md must have non-trivial content"
    assert "#" in arch_text, "ARCHITECTURE.md must contain a markdown heading"

    # AC3: sub-tracks dispatched sequentially (mock fixture includes requires: [database, security])
    sub_tracks_dir = tmp_path / "02-Architecture" / "02-System" / "sub-tracks"
    assert sub_tracks_dir.is_dir()
    sub_files = sorted(sub_tracks_dir.glob("*.md"))
    assert len(sub_files) >= 1, f"Expected ≥1 sub-track files, got: {[f.name for f in sub_files]}"

    # AC6: journal has agent_dispatched + artifact_written entries
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    assert len(dispatched) >= 2, "journal must have primary + at least 1 sub-track dispatch"
    assert any(e["payload"]["specialist"] == "system-architect" for e in dispatched)
    assert len(written) >= 2, "journal must have artifact_written for each dispatch"
    for e in written:
        assert e["actor"] == "cli"
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 2

    # AC1: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 2
    assert out["track"] == "architect"
    assert out["specialist"] == "system-architect"
    assert out["outcome"] == "success"
    assert out["architecture_path"] == "02-Architecture/02-System/ARCHITECTURE.md"
    assert isinstance(out["sub_tracks_dispatched"], list)
    assert isinstance(out["sub_track_artifacts"], list)
    assert len(out["sub_track_artifacts"]) == len(out["sub_tracks_dispatched"])

    # AC8 anti-tautology: each sub-track artifact path matches the declared track name
    for artifact in out["sub_track_artifacts"]:
        assert "track" in artifact
        assert "path" in artifact
        assert artifact["track"] in artifact["path"]


# ---------------------------------------------------------------------------
# Phase 1 gate: phase 1 not approved → ERR_PHASE1_NOT_APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_architect_integration_requires_phase1_approved(tmp_path: Path) -> None:
    """AC1: sdlc architect refuses with ERR_PHASE1_NOT_APPROVED when phase 1 not approved."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF

    result = _invoke_architect(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (result.stdout + (result.stderr or ""))

    # No architecture files must be written
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    if arch_dir.exists():
        assert not (arch_dir / "ARCHITECTURE.md").is_file()


# ---------------------------------------------------------------------------
# Unknown sub-track: full pipeline with a primary declaring an unknown track
# (code review CR14-P16 — previously only unit-tier covered this path).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_architect_integration_unknown_sub_track(tmp_path: Path) -> None:
    """AC3: an unknown declared sub-track fails the run; ARCHITECTURE.md still written."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    patched = functools.partial(_ap.materialize_primary_mock, requires=("quantum-computing",))
    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.architect.materialize_primary_mock", patched),
    ):
        result = _runner.invoke(app, ["--json", "architect"])

    assert result.exit_code == 1
    output = result.stdout + (result.stderr or "")
    assert "ERR_UNKNOWN_SUB_TRACK" in output
    assert "quantum-computing" in output

    # ARCHITECTURE.md IS written (primary dispatch succeeded before validation)
    arch_path = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_path.is_file()

    # No sub-track files written
    sub_dir = tmp_path / "02-Architecture" / "02-System" / "sub-tracks"
    assert not sub_dir.is_dir() or not list(sub_dir.glob("*.md"))

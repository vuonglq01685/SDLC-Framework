"""Integration tests for ``sdlc bootstrap`` (Story 2A.15, AC1-AC10)."""

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


def _write_architecture_md(tmp_path: Path) -> Path:
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    arch_dir.mkdir(parents=True, exist_ok=True)
    p = arch_dir / "ARCHITECTURE.md"
    p.write_text("# System Architecture\n\nMinimal architecture for testing.\n", encoding="utf-8")
    return p


def _approve_phase(tmp_path: Path, phase: int, artifact_path: Path, artifact_key: str) -> None:
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_key, hash=artifact_hash),),
        approved_by="integration-test",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _invoke_bootstrap(tmp_path: Path, *, json_mode: bool = True) -> object:
    args = ["--json", "bootstrap"] if json_mode else ["bootstrap"]
    with unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path):
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
def test_sdlc_bootstrap_integration_full_pipeline(tmp_path: Path) -> None:
    """AC1/AC3/AC5/AC7: full pipeline — src/ populated, journal sequence correct."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    arch_path = _write_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")

    result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: src/ populated with at least one real file
    src_dir = tmp_path / "src"
    assert src_dir.is_dir()
    real_files = [
        p for p in src_dir.rglob("*") if p.is_file() and p.name not in {".gitkeep", "README.md"}
    ]
    assert len(real_files) >= 1, "src/ must contain at least one real (non-placeholder) file"

    # AC7: journal has agent_dispatched → artifact_written(s) → bootstrap_completed
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    completed = [e for e in entries if e["kind"] == "bootstrap_completed"]

    assert any(e["payload"]["specialist"] == "code-bootstrapper" for e in dispatched), (
        "journal must have agent_dispatched for code-bootstrapper"
    )
    assert len(written) >= 1, "journal must have at least one artifact_written entry"
    for e in written:
        assert e["actor"] == "cli"
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 3
    assert len(completed) == 1, "journal must have exactly one bootstrap_completed entry"
    bc = completed[0]
    assert bc["payload"]["files_written"] >= 1
    assert bc["payload"]["specialist"] == "code-bootstrapper"

    # Sequence: all dispatched entries precede all written entries in journal order
    dispatch_seqs = [
        e["monotonic_seq"]
        for e in dispatched
        if e["payload"].get("specialist") == "code-bootstrapper"
    ]
    written_seqs = [e["monotonic_seq"] for e in written]
    completed_seq = bc["monotonic_seq"]
    assert dispatch_seqs, "missing agent_dispatched seq"
    assert max(dispatch_seqs) < min(written_seqs), "dispatched must precede written"
    assert max(written_seqs) < completed_seq, "written must precede bootstrap_completed"

    # AC1: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 3
    assert out["track"] == "bootstrap"
    assert out["specialist"] == "code-bootstrapper"
    assert out["outcome"] == "success"
    assert isinstance(out["files_written"], int)
    assert out["files_written"] >= 1
    assert out["source_root"] == "src"

    # files_written matches journal bootstrap_completed
    assert out["files_written"] == bc["payload"]["files_written"]


# ---------------------------------------------------------------------------
# Auto-skip: source already exists → exit 0, no dispatch
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_bootstrap_integration_auto_skip(tmp_path: Path) -> None:
    """AC2: when src/ contains a real file, command exits 0 with reason=source-exists."""
    _init_repo(tmp_path)
    _write_product_md(tmp_path)
    # Populate src/ with a real file — no Phase 2 signoff needed (AC2 invariant)
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text("# existing source\n", encoding="utf-8")

    result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    out = json.loads(result.stdout)
    assert out["outcome"] == "skipped"
    assert out["reason"] == "source-exists"
    assert out["phase"] == 3

    # No dispatch journal entries
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    assert dispatched == [], "auto-skip must not journal agent_dispatched"


# ---------------------------------------------------------------------------
# Phase 2 gate: not approved + empty src → ERR_PHASE2_NOT_APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_bootstrap_integration_requires_phase2_approved(tmp_path: Path) -> None:
    """AC1: sdlc bootstrap refuses with ERR_PHASE2_NOT_APPROVED when phase 2 not approved."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    _write_architecture_md(tmp_path)
    # Phase 1 approved, but NOT phase 2
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")

    result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE2_NOT_APPROVED" in (result.stdout + (result.stderr or ""))

    # No real files written under src/
    src_dir = tmp_path / "src"
    if src_dir.exists():
        real = [
            p for p in src_dir.rglob("*") if p.is_file() and p.name not in {".gitkeep", "README.md"}
        ]
        assert real == [], "no real source files must be written when phase 2 not approved"


# ---------------------------------------------------------------------------
# P8 — Hook denial during file-write loop
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_bootstrap_integration_hook_deny_mid_batch(tmp_path: Path) -> None:
    """P8 (D1 debt): pre-write hook denial → ERR_BOOTSTRAP_DISPATCH_FAILED, exit 1."""
    from sdlc.hooks.runner import HookDecision

    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    arch_path = _write_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")

    deny = HookDecision.deny(
        hook_name="test-deny-hook",
        reason="integration test deny",
        error_code="phase_gate_violation",
    )
    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli._bootstrap_pipeline.run_hook_chain",
            new=unittest.mock.AsyncMock(return_value=deny),
        ),
    ):
        r = _runner.invoke(app, ["--json", "bootstrap"])

    assert r.exit_code == 1
    assert "ERR_BOOTSTRAP_DISPATCH_FAILED" in (r.stdout + (r.stderr or ""))

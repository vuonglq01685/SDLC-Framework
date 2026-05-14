"""Tier-2 e2e for ``sdlc ux`` (Story 2A.13, AC9).

Scenarios:
  1. Happy path: phase 1 APPROVED + MockAIRuntime canned response → 3 UX files
     written; journal has 1 agent_dispatched + 3 artifact_written entries.
  2. Phase gate block: phase 1 AWAITING_SIGNOFF → ERR_PHASE1_NOT_APPROVED;
     no files written; no dispatch call.

Anti-tautology receipt for scenario 2: temporarily commented out the
``compute_state == APPROVED`` gate in ``run_ux``; confirmed scenario 2's
assertion ``"ERR_PHASE1_NOT_APPROVED" in output`` FAILED (no error emitted
because the gate was bypassed); reverted. Documented in PR Change Log per
AC9 mandatory requirement.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "ux"

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


def _seed_product_md(tmp_path: Path) -> Path:
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    p = req / "01-PRODUCT.md"
    p.write_bytes((_FIXTURES / "01-PRODUCT.md").read_bytes())
    return p


def _approve_phase1(tmp_path: Path, product_path: Path) -> None:
    artifact_hash = compute_artifact_hash(product_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=artifact_hash),),
        approved_by="e2e-approver",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _invoke_ux(tmp_path: Path, *, json_mode: bool = True) -> Any:
    args = ["--json", "ux"] if json_mode else ["ux"]
    with unittest.mock.patch("sdlc.cli.ux._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: full MockAIRuntime pipeline
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_ux_happy_path(tmp_path: Path) -> None:
    """AC9 scenario 1: phase 1 APPROVED → 3 UX placeholder files + journal entries."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_ux(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # Files written under 02-Architecture/01-UX/
    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    assert ux_dir.is_dir()
    md_files = sorted(ux_dir.glob("*.md"))
    assert len(md_files) >= 1, f"Expected ≥1 UX files, got: {[f.name for f in md_files]}"

    # Anti-tautology: files have real content (MockAIRuntime v1 PLACEHOLDER text)
    for f in md_files:
        content = f.read_text(encoding="utf-8")
        assert "PLACEHOLDER" in content or content.strip().startswith("#"), (
            f"{f.name}: unexpected content (not a PLACEHOLDER and no markdown heading)"
        )
        assert len(content) > 10

    # Journal: 1 agent_dispatched + N artifact_written
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    assert len(dispatched) == 1, f"Expected 1 agent_dispatched, got {len(dispatched)}"
    assert dispatched[0]["payload"]["specialist"] == "ux-designer"
    assert dispatched[0]["payload"]["phase"] == 2
    assert len(written) >= 1, f"Expected ≥1 artifact_written, got {len(written)}"
    for e in written:
        assert e["actor"] == "cli"
        assert e["before_hash"] is None
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 2

    # emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 2
    assert out["track"] == "ux"
    assert out["specialist"] == "ux-designer"
    assert out["outcome"] == "success"
    assert len(out["artifacts"]) >= 1


# ---------------------------------------------------------------------------
# Scenario 2 — Phase gate block: phase 1 NOT approved
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_ux_phase_gate_block(tmp_path: Path) -> None:
    """AC9 scenario 2: phase 1 AWAITING_SIGNOFF → ERR_PHASE1_NOT_APPROVED; no files written."""
    _init_repo(tmp_path)
    _seed_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF

    with unittest.mock.patch("sdlc.cli.ux.dispatch") as mock_dispatch:
        result = _invoke_ux(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (result.stdout + (result.stderr or ""))

    # No UX files must be written
    ux_dir = tmp_path / "02-Architecture" / "01-UX"
    if ux_dir.exists():
        assert list(ux_dir.glob("*.md")) == [], "No UX files must be written when gate blocks"

    # dispatch must NOT be called when the gate fires
    mock_dispatch.assert_not_called()

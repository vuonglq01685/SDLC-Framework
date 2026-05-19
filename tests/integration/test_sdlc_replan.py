"""Integration tests for sdlc replan (Story 2A.19, Task 3.3).

Uses real tmp_path with approved Phase 1 + Phase 2 signoff records.
Invokes run_replan directly and asserts:
  - signoff YAML files gain invalidated_at
  - journal sequence: replan_invalidated before signoff_invalidated
  - JSON output shape
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
import typer

pytestmark = pytest.mark.integration


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_and_approve(tmp_path: Path, phase: int, rel_path: str) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Phase {phase} artifact stub\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(p, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=rel_path, hash=artifact_hash),),
        approved_by="integration-approver",
        approved_at="2026-05-19T10:00:00.000Z",
        drafted_at="2026-05-19T09:00:00.000Z",
        validated_at="2026-05-19T10:00:00.000Z",
    )
    write_record(record, repo_root=tmp_path)


def _invoke_replan(tmp_path: Path, scope: str) -> dict:
    """Invoke run_replan and return parsed JSON output."""
    from typer.testing import CliRunner

    from sdlc.cli.main import app

    runner = CliRunner()
    args = ["--json", "replan", "--scope", scope]
    with unittest.mock.patch("sdlc.cli.replan_cmd._get_repo_root_or_cwd", return_value=tmp_path):
        result = runner.invoke(app, args)
    assert result.exit_code == 0, f"replan failed: {result.output}"
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# Integration scenario: phase 2 replan invalidates the YAML file
# ---------------------------------------------------------------------------


def test_integration_phase2_replan_writes_invalidated_at(tmp_path: Path) -> None:
    """After replan, the phase-2 signoff YAML has invalidated_at set."""
    import yaml

    _init_repo(tmp_path)
    product_rel = "01-Requirement/01-PRODUCT.md"
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 1, product_rel)
    _seed_and_approve(tmp_path, 2, arch_rel)

    _invoke_replan(tmp_path, arch_rel)

    # Phase 2 signoff YAML should have invalidated_at
    signoff_path = tmp_path / ".claude" / "state" / "signoffs" / "phase-2.yaml"
    assert signoff_path.exists()
    data = yaml.safe_load(signoff_path.read_text(encoding="utf-8"))
    assert data["invalidated_at"] is not None
    assert data["invalidated_reason"] is not None

    # Phase 1 signoff YAML should NOT have invalidated_at
    phase1_path = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    assert phase1_path.exists()
    data1 = yaml.safe_load(phase1_path.read_text(encoding="utf-8"))
    assert data1.get("invalidated_at") is None


def test_integration_journal_sequence_replan_before_signoff(tmp_path: Path) -> None:
    """replan_invalidated entry appears before signoff_invalidated in journal."""
    _init_repo(tmp_path)
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 2, arch_rel)

    _invoke_replan(tmp_path, arch_rel)

    from sdlc.journal import iter_entries

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = list(iter_entries(journal_path))
    replan_kinds = ["replan_invalidated", "signoff_invalidated"]
    replan_entries = [e for e in entries if e.kind in replan_kinds]

    # replan_invalidated must come first
    assert replan_entries[0].kind == "replan_invalidated"
    assert replan_entries[0].monotonic_seq < replan_entries[1].monotonic_seq


def test_integration_phase1_replan_json_output(tmp_path: Path) -> None:
    """Phase 1 scope → JSON envelope lists both phases in invalidated_phases."""
    _init_repo(tmp_path)
    product_rel = "01-Requirement/01-PRODUCT.md"
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 1, product_rel)
    _seed_and_approve(tmp_path, 2, arch_rel)

    data = _invoke_replan(tmp_path, product_rel)
    assert data["command"] == "replan"
    assert data["scope"] == product_rel
    assert data["scope_phase"] == 1
    assert sorted(data["invalidated_phases"]) == [1, 2]
    assert data["outcome"] == "success"

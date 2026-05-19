"""Tier-2 e2e for ``sdlc replan --scope`` (Story 2A.19, AC5, AC7, AC10).

Four scenarios per AC10:
  1. Phase 2 scope: phase 1+2 APPROVED → replan phase-2 artifact →
     only phase 2 invalidated; journal chain = replan_invalidated → signoff_invalidated;
     JSON envelope has scope_phase=2, invalidated_phases=[2].
  2. Phase 1 scope: phase 1+2 APPROVED → replan phase-1 artifact →
     both phases 1+2 invalidated; JSON envelope has invalidated_phases=[1, 2].
  3. AC5 phase-gate: after a phase-2 replan, ``sdlc break`` refuses with
     ERR_PHASE2_NOT_APPROVED — the phase-gate already blocks Phase 3 writes.
  4. AC7 re-sign round-trip: after phase-2 replan, ``write_record`` writes a
     fresh approved record; ``compute_state(2)`` returns APPROVED again.

Anti-tautology receipt (AC10 mandatory):
  ``test_e2e_replan_invalidation_is_load_bearing``:
  Without neutralisation: phase-2 YAML gains ``invalidated_at`` → test passes.
  With ``invalidate_record`` neutralised (no-op): YAML keeps ``invalidated_at=None``
  and the baseline assertion fails — confirming the call, not just the replan
  journal event, drives the signoff mutation.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.signoff.states import SignoffState, compute_state

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_STORY_ID = "EPIC-replan-S01-story"
_TS1 = "2026-05-19T09:00:00.000Z"
_TS2 = "2026-05-19T10:00:00.000Z"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_and_approve(tmp_path: Path, phase: int, rel_path: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Phase {phase} artifact stub\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(p, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=rel_path, hash=artifact_hash),),
        approved_by="e2e-approver",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)
    return p


def _invoke_replan(
    tmp_path: Path,
    scope: str,
    *,
    json_mode: bool = True,
) -> Any:
    args = ["--json", "replan", "--scope", scope] if json_mode else ["replan", "--scope", scope]
    with unittest.mock.patch("sdlc.cli.replan_cmd._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _invoke_break(tmp_path: Path, story_id: str = _STORY_ID) -> Any:
    with unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, ["--json", "break", story_id])


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _read_signoff_yaml(tmp_path: Path, phase: int) -> dict[str, Any]:
    p = tmp_path / ".claude" / "state" / "signoffs" / f"phase-{phase}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Scenario 1 — Phase 2 scope: only phase 2 invalidated
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_replan_phase2_scope_invalidates_phase2_only(tmp_path: Path) -> None:
    """AC10 scenario 1: phase-2 scoped replan leaves phase 1 intact.

    Setup: phase 1 + phase 2 both APPROVED.
    Replan scope: 02-Architecture artifact → scope_phase=2.
    Expected: phase 2 YAML gains invalidated_at; phase 1 YAML unchanged.
    Journal chain: replan_invalidated (seq N) → signoff_invalidated (seq N+1).
    JSON envelope: scope_phase=2, invalidated_phases=[2], downstream_count≥0.
    """
    _init_repo(tmp_path)
    _seed_and_approve(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 2, arch_rel)

    result = _invoke_replan(tmp_path, arch_rel)
    assert result.exit_code == 0, result.output

    data = json.loads(result.output)
    assert data["command"] == "replan"
    assert data["scope_phase"] == 2
    assert data["invalidated_phases"] == [2]
    assert data["outcome"] == "success"

    # Phase 2 YAML must have invalidated_at set
    p2 = _read_signoff_yaml(tmp_path, 2)
    assert p2["invalidated_at"] is not None
    assert p2["invalidated_reason"] is not None

    # Phase 1 YAML must remain clean (invalidated_at absent or None)
    p1 = _read_signoff_yaml(tmp_path, 1)
    assert p1.get("invalidated_at") is None

    # Journal chain: replan_invalidated first, then signoff_invalidated
    entries = _read_journal(tmp_path)
    replan_entries = [
        e for e in entries if e["kind"] in {"replan_invalidated", "signoff_invalidated"}
    ]
    assert len(replan_entries) == 2
    assert replan_entries[0]["kind"] == "replan_invalidated"
    assert replan_entries[0]["monotonic_seq"] < replan_entries[1]["monotonic_seq"]
    assert replan_entries[1]["kind"] == "signoff_invalidated"
    assert replan_entries[1]["payload"]["phase"] == 2


# ---------------------------------------------------------------------------
# Scenario 2 — Phase 1 scope: both phases 1 and 2 invalidated
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_replan_phase1_scope_invalidates_both_phases(tmp_path: Path) -> None:
    """AC10 scenario 2: phase-1 scoped replan invalidates phases 1 and 2.

    scope_phase=1 → plan_invalidations returns [1, 2] (all APPROVED phases >= 1).
    Both phase-1 and phase-2 YAMLs gain invalidated_at.
    JSON envelope: invalidated_phases=[1, 2].
    Journal has: 1x replan_invalidated + 2x signoff_invalidated.
    """
    _init_repo(tmp_path)
    product_rel = "01-Requirement/01-PRODUCT.md"
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 1, product_rel)
    _seed_and_approve(tmp_path, 2, arch_rel)

    result = _invoke_replan(tmp_path, product_rel)
    assert result.exit_code == 0, result.output

    data = json.loads(result.output)
    assert data["scope_phase"] == 1
    assert sorted(data["invalidated_phases"]) == [1, 2]
    assert data["downstream_count"] >= 1  # at least the arch artifact

    # Both YAMLs must be invalidated
    for phase in (1, 2):
        yaml_data = _read_signoff_yaml(tmp_path, phase)
        assert yaml_data["invalidated_at"] is not None, f"phase {phase} not invalidated"

    # Journal: 1 replan_invalidated + 2 signoff_invalidated
    entries = _read_journal(tmp_path)
    replan_evts = [e for e in entries if e["kind"] == "replan_invalidated"]
    signoff_evts = [e for e in entries if e["kind"] == "signoff_invalidated"]
    assert len(replan_evts) == 1
    assert len(signoff_evts) == 2
    # replan event appears before both signoff events
    replan_seq = replan_evts[0]["monotonic_seq"]
    for si in signoff_evts:
        assert replan_seq < si["monotonic_seq"]


# ---------------------------------------------------------------------------
# Scenario 3 — AC5 phase-gate: sdlc break refuses after replan
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_replan_phase_gate_blocks_break_after_invalidation(tmp_path: Path) -> None:
    """AC10 scenario 3 (AC5): post-replan, ``sdlc break`` refuses with ERR_PHASE2_NOT_APPROVED.

    After invalidating phase 2, ``compute_state(2)`` returns INVALIDATED_BY_REPLAN
    which != APPROVED.  ``break_.py:Step 3`` (phase-2 gate) fires before any
    story lookup, so a validly-formatted story id is sufficient — no story file needed.
    No code change to phase_gate.py required; 2A.19 verifies the existing guard.
    """
    _init_repo(tmp_path)
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_and_approve(tmp_path, 2, arch_rel)

    # Confirm phase 2 is APPROVED before replan
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.APPROVED

    replan_result = _invoke_replan(tmp_path, arch_rel)
    assert replan_result.exit_code == 0, replan_result.output

    # Phase 2 must now be INVALIDATED_BY_REPLAN
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

    # sdlc break must refuse with ERR_PHASE2_NOT_APPROVED
    break_result = _invoke_break(tmp_path)
    assert break_result.exit_code == 1
    out = break_result.stdout + (break_result.stderr or "")
    assert "ERR_PHASE2_NOT_APPROVED" in out, (
        f"expected ERR_PHASE2_NOT_APPROVED in output; got: {out}"
    )


# ---------------------------------------------------------------------------
# Scenario 4 — AC7 re-sign round-trip restores APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_replan_resign_round_trip_restores_approved(tmp_path: Path) -> None:
    """AC10 scenario 4 (AC7): writing a fresh signoff record after replan → APPROVED.

    ``write_record`` (records.py:262) permits overwriting a record whose
    ``invalidated_at`` is non-null (Story 2A.7 D4: 'invalidated overwrite allowed').
    This test calls ``write_record`` directly to simulate what ``sdlc signoff 2``
    does after the user re-approves: it verifies the round-trip mechanism works
    and that 2A.19 does not regress it.  No new re-sign code is implemented by 2A.19.
    """
    _init_repo(tmp_path)
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    arch_path = _seed_and_approve(tmp_path, 2, arch_rel)

    # Replan invalidates phase 2
    replan_result = _invoke_replan(tmp_path, arch_rel)
    assert replan_result.exit_code == 0, replan_result.output
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

    # Re-sign: compute fresh hash and write a new approved record
    fresh_hash = compute_artifact_hash(arch_path, repo_root=tmp_path)
    fresh_record = SignoffRecord(
        phase=2,
        artifacts=(ArtifactRef(path=arch_rel, hash=fresh_hash),),
        approved_by="re-approver",
        approved_at="2026-05-19T12:00:00.000Z",
        drafted_at="2026-05-19T11:00:00.000Z",
        validated_at="2026-05-19T12:00:00.000Z",
    )
    write_record(fresh_record, repo_root=tmp_path)

    # Phase 2 must be APPROVED again
    assert compute_state(phase=2, repo_root=tmp_path) == SignoffState.APPROVED

    # YAML must not retain invalidated_at from before
    yaml_data = _read_signoff_yaml(tmp_path, 2)
    assert yaml_data.get("invalidated_at") is None
    assert yaml_data["approved_by"] == "re-approver"


# ---------------------------------------------------------------------------
# Anti-tautology receipt — invalidate_record call is load-bearing
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_replan_invalidation_is_load_bearing(tmp_path: Path) -> None:
    """AC10 anti-tautology receipt: the ``invalidate_record`` call drives the YAML mutation.

    Proof structure (executable form):

    Baseline (no neutralisation):
      ``sdlc replan`` runs normally → phase-2 YAML gains ``invalidated_at``.
      The baseline assertion passes.

    Mutation (``invalidate_record`` neutralised to no-op):
      The ``replan_invalidated`` journal event IS still written (so the command
      does not fail), but ``invalidate_record`` is never called → YAML keeps
      ``invalidated_at=None``.  The baseline assertion WOULD fail — confirming
      that the journal write alone is not sufficient; ``invalidate_record`` is
      the load-bearing call that actually mutates the signoff state.

    The mutation branch is verified inside this test so the receipt is executable.
    """
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"

    # --- Baseline: without neutralisation ---
    _init_repo(tmp_path)
    _seed_and_approve(tmp_path, 2, arch_rel)
    result_normal = _invoke_replan(tmp_path, arch_rel)
    assert result_normal.exit_code == 0, result_normal.output
    p2_normal = _read_signoff_yaml(tmp_path, 2)
    assert p2_normal["invalidated_at"] is not None, (
        "baseline: phase-2 YAML must have invalidated_at after replan"
    )

    # --- Mutation: neutralise invalidate_record → no-op ---
    tmp2 = tmp_path / "mutation"
    tmp2.mkdir()
    _init_repo(tmp2)
    _seed_and_approve(tmp2, 2, arch_rel)

    # replan_cmd imports invalidate_record at module level:
    #   from sdlc.signoff.records import invalidate_record
    # The patch must target the name in replan_cmd's namespace, not in records.
    noop_record = unittest.mock.MagicMock()
    noop_record.invalidated_at = "2026-05-19T10:00:00.000Z"

    with (
        unittest.mock.patch("sdlc.cli.replan_cmd._get_repo_root_or_cwd", return_value=tmp2),
        unittest.mock.patch("sdlc.cli.replan_cmd.invalidate_record", return_value=noop_record),
    ):
        result_mutated = _runner.invoke(app, ["--json", "replan", "--scope", arch_rel])

    assert result_mutated.exit_code == 0, (
        f"neutralised run must still exit 0 (journal write succeeds): {result_mutated.output}"
    )
    p2_mutated = _read_signoff_yaml(tmp2, 2)
    assert p2_mutated.get("invalidated_at") is None, (
        "anti-tautology breach: YAML gained invalidated_at even with invalidate_record "
        "neutralised — the signoff mutation comes from somewhere other than invalidate_record"
    )

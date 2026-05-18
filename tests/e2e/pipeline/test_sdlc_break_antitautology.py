"""AC10 anti-tautology receipts for ``sdlc break`` (Story 2A.16, Task 5).

Executable proofs that the active-status guard and the seq-contiguity check
are each individually load-bearing (not test-only artefacts):

  - ``test_e2e_break_active_status_check_is_load_bearing``: neutralises
    ``_story_is_active`` → a "done" story must NOT be rejected with "not active".
  - ``test_e2e_break_seq_contiguity_check_is_load_bearing``: neutralises the
    seq-contiguity assertion inside ``_validate_task_batch`` → a T01+T03 gap
    batch must NOT fail with "seq gap".
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

_FIXTURES = Path(__file__).parent / "fixtures" / "break"

_STORY_ID = "EPIC-e2ebreak-S01-user-auth"
_EPIC_ID = "EPIC-e2ebreak"

_TS1 = "2026-05-18T09:00:00.000Z"
_TS2 = "2026-05-18T10:00:00.000Z"


# ---------------------------------------------------------------------------
# Helpers (shared with test_sdlc_break.py — duplicated to keep files independent)
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


def _seed_architecture_md(tmp_path: Path) -> Path:
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    arch_dir.mkdir(parents=True, exist_ok=True)
    p = arch_dir / "ARCHITECTURE.md"
    p.write_text("# System Architecture\n\nMinimal e2e stub.\n", encoding="utf-8")
    return p


def _seed_story_json(
    tmp_path: Path,
    story_id: str = _STORY_ID,
    status: str = "in-progress",
) -> Path:
    src = _FIXTURES / f"{story_id}.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    data["status"] = status
    story_dir = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    story_dir.mkdir(parents=True, exist_ok=True)
    p = story_dir / f"{story_id}.json"
    p.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    return p


def _approve_phase(tmp_path: Path, phase: int, artifact_path: Path, artifact_key: str) -> None:
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_key, hash=artifact_hash),),
        approved_by="e2e-approver",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _invoke_break(tmp_path: Path, story_id: str = _STORY_ID, *, json_mode: bool = True) -> Any:
    args = ["--json", "break", story_id] if json_mode else ["break", story_id]
    with unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _ready_approved_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    arch_path = _seed_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")


# ---------------------------------------------------------------------------
# Anti-tautology receipt 1: active-status check is load-bearing
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_active_status_check_is_load_bearing(tmp_path: Path) -> None:
    """AC10 anti-tautology receipt 1 (executable form).

    Mutation: patch ``_story_is_active`` to always return True, then run with
    a story where status="done" (normally rejected with 'not active').
    With the guard neutralised the command MUST NOT fail with 'not active' —
    proving ``_story_is_active``, and only it, causes the refusal in scenario 2.
    The command will fail for a different reason (phase 2 gate, if no signoff)
    or succeed entirely — either way it did not die on the status check.

    Because phase 2 IS approved in this setup and the mock runtime runs,
    the command reaches dispatch and succeeds — which is the strongest form
    of proof that the status guard was the only barrier.
    """
    _ready_approved_repo(tmp_path)
    # Story with status="done" — normally rejected at the status check
    _seed_story_json(tmp_path, status="done")

    # Without neutralisation: should fail
    result_normal = _invoke_break(tmp_path)
    assert result_normal.exit_code == 1
    assert "not active" in (result_normal.stdout + (result_normal.stderr or "")).lower(), (
        "baseline: 'done' story must fail with 'not active' before mutation"
    )

    # Neutralise _story_is_active → always returns True
    with unittest.mock.patch("sdlc.cli.break_._story_is_active", return_value=True):
        result_mutated = _invoke_break(tmp_path)

    out_text = result_mutated.stdout + (result_mutated.stderr or "")
    # Guard neutralised → 'not active' refusal must NOT appear
    assert "not active" not in out_text.lower(), (
        "anti-tautology breach: 'not active' error still raised with _story_is_active neutralised"
    )
    # Strongest proof: with the guard the sole barrier, the run reaches dispatch
    # and succeeds — exit 0 and 3 task files written.
    assert result_mutated.exit_code == 0, (
        f"with _story_is_active neutralised the command must succeed; got: {out_text}"
    )
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    written = sorted(p.name for p in tasks_dir.glob("T*-*.json"))
    assert len(written) == 3, f"expected 3 task files after mutation; got {written}"


# ---------------------------------------------------------------------------
# Anti-tautology receipt 2: seq-contiguity check is load-bearing
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_seq_contiguity_check_is_load_bearing(tmp_path: Path) -> None:  # noqa: C901
    """AC10 anti-tautology receipt 2 (executable form).

    Mutation: wrap ``_validate_task_batch`` to skip the seq-contiguity assertion,
    then inject a batch with T01+T03 (gap — normally rejected with 'seq gap').
    With the check neutralised the command MUST NOT fail with 'seq gap' —
    proving the seq-contiguity check, and only it, causes that refusal.
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path, status="in-progress")

    # Gap batch: T01 + T03, skip T02
    gap_batch = json.dumps(
        [
            {
                "id": f"{_STORY_ID}-T01-first-task",
                "story_id": _STORY_ID,
                "label": "First task.",
                "stage": "pending",
                "dependencies": [],
            },
            {
                "id": f"{_STORY_ID}-T03-third-task",
                "story_id": _STORY_ID,
                "label": "Third task (skips T02).",
                "stage": "pending",
                "dependencies": [],
            },
        ]
    )
    dispatch_result = unittest.mock.MagicMock()
    dispatch_result.outcome = "success"
    dispatch_result.agent_result.output_text = gap_batch

    # Without neutralisation: should fail with seq gap
    with unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result):
        result_normal = _invoke_break(tmp_path)

    assert result_normal.exit_code == 1
    assert "seq gap" in (result_normal.stdout + (result_normal.stderr or "")).lower(), (
        "baseline: T01+T03 batch must fail with 'seq gap' before mutation"
    )

    import sdlc.cli._break_pipeline as _pipeline_mod

    def _validate_no_seq(records: list, *, request_story_id: str) -> None:
        """Wrapped validator: runs every real check EXCEPT seq contiguity."""
        from sdlc.errors import WorkflowError

        if not records:
            raise WorkflowError("empty batch", details={"sdlc_break": "empty_batch"})
        seen_ids: set = set()
        for rec in records:
            if rec.story_id != request_story_id:
                raise WorkflowError("wrong story_id", details={"sdlc_break": "wrong_story_id"})
            if rec.id in seen_ids:
                raise WorkflowError(
                    "duplicate task id", details={"sdlc_break": "duplicate_task_id"}
                )
            seen_ids.add(rec.id)
        for rec in records:
            for dep in rec.dependencies:
                if dep not in seen_ids:
                    raise WorkflowError("orphan dep", details={"sdlc_break": "orphan_dependency"})
        # Real DAG check stays active — only seq contiguity is neutralised.
        _pipeline_mod._check_dep_dag(records)

    with (
        unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli._break_pipeline.dispatch", return_value=dispatch_result),
        unittest.mock.patch(
            "sdlc.cli._break_pipeline._validate_task_batch", side_effect=_validate_no_seq
        ),
        unittest.mock.patch("sdlc.cli.break_.evaluate_postconditions"),
    ):
        result_mutated = _runner.invoke(app, ["--json", "break", _STORY_ID])

    out_text = result_mutated.stdout + (result_mutated.stderr or "")
    # Check neutralised → 'seq gap' error must NOT appear
    assert "seq gap" not in out_text.lower(), (
        "anti-tautology breach: 'seq gap' error still raised with seq check neutralised"
    )

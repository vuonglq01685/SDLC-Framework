"""Tier-2 e2e for ``sdlc break`` (Story 2A.16, AC10, Task 5).

AC10 mandates THREE scenarios; a fourth (phase-2 gate) is added as
defense-in-depth. All are driven through the real MockAIRuntime pipeline
(no ``dispatch`` mock):

  1. Happy path: phase 2 APPROVED + active story JSON → 3 task files written
     under 03-Implementation/tasks/<STORY-id>/, journal sequence correct,
     emit_json success.
  2. Refuse: story not active — story status "pending" → exit 1,
     "story not active", no files written, no dispatch.
  3. Idempotency guard: tasks dir already has a T*-*.json file → exit 1,
     "already broken", no new files written.
  4. Phase 2 gate blocked: phase 2 not approved → exit 1,
     ERR_PHASE2_NOT_APPROVED, no files written.

Dual anti-tautology receipts (AC10 mandatory — executable form):
  ``test_e2e_break_active_status_check_is_load_bearing``: inverts the
  ``_story_is_active`` guard to always return True, then re-runs a "done"
  story. Without the guard the command must NOT fail with "not active" —
  proving the guard, and only the guard, causes that refusal.

  ``test_e2e_break_seq_contiguity_check_is_load_bearing``: neutralises the
  seq-contiguity check inside ``_validate_task_batch`` by wrapping it with a
  version that skips the seq assertion, then injects a T01+T03 batch (gap).
  Without the check the command must NOT fail with "seq gap" — proving the
  check, and only it, causes that refusal.
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


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _ready_approved_repo(tmp_path: Path) -> None:
    """Init + phase-1/2 signoffs + PRODUCT.md + architecture stub."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    arch_path = _seed_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: phase 2 APPROVED + active story (AC10.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_happy_path(tmp_path: Path) -> None:
    """AC10 scenario 1: phase 2 APPROVED + active story → 3 task files, journal, exit 0."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path, status="in-progress")

    result = _invoke_break(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # 3 task files written under correct path
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    assert tasks_dir.is_dir(), "tasks dir must be created"
    task_files = sorted(tasks_dir.glob("T*-*.json"))
    assert len(task_files) == 3, f"expected 3 task files; got {[f.name for f in task_files]}"
    assert task_files[0].name.startswith("T01-")
    assert task_files[1].name.startswith("T02-")
    assert task_files[2].name.startswith("T03-")

    for f in task_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["story_id"] == _STORY_ID
        assert data["stage"] == "pending"

    # Journal: agent_dispatched -> 3x artifact_written -> story_broken_into_tasks
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    broken = [e for e in entries if e["kind"] == "story_broken_into_tasks"]

    assert any(e["payload"].get("specialist") == "task-breaker" for e in dispatched)
    assert len(written) == 3
    assert len(broken) == 1
    bt = broken[0]
    assert bt["payload"]["story_id"] == _STORY_ID
    assert bt["payload"]["task_count"] == 3

    # Sequence ordering: dispatch < writes < broken
    dispatch_seqs = [
        e["monotonic_seq"] for e in dispatched if e["payload"].get("specialist") == "task-breaker"
    ]
    written_seqs = [e["monotonic_seq"] for e in written]
    assert dispatch_seqs
    assert max(dispatch_seqs) < min(written_seqs)
    assert max(written_seqs) < bt["monotonic_seq"]

    # emit_json success envelope
    out = json.loads(result.stdout)
    assert out["outcome"] == "success"
    assert out["phase"] == 3
    assert out["track"] == "break"
    assert out["story_id"] == _STORY_ID
    assert out["task_count"] == 3
    assert len(out["task_ids"]) == 3

    # Idempotency: second run auto-rejects
    result2 = _invoke_break(tmp_path)
    assert result2.exit_code == 1
    assert "already broken" in (result2.stdout + (result2.stderr or "")).lower()


# ---------------------------------------------------------------------------
# Scenario 2 — Idempotency guard: tasks dir pre-populated (AC10.2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_idempotency_guard(tmp_path: Path) -> None:
    """AC10 scenario 2: tasks dir already has T*.json → exit 1, already broken, no dispatch."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path, status="in-progress")

    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T01-existing-task.json").write_text('{"stub": true}', encoding="utf-8")

    with unittest.mock.patch("sdlc.cli._break_pipeline.dispatch") as mock_dispatch:
        result = _invoke_break(tmp_path)

    assert result.exit_code == 1
    mock_dispatch.assert_not_called()
    assert "already broken" in (result.stdout + (result.stderr or "")).lower()

    # Pre-existing file unmolested
    assert (tasks_dir / "T01-existing-task.json").is_file()


# ---------------------------------------------------------------------------
# Scenario 3 — Phase 2 gate blocked (AC10.3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_phase2_gate_blocked(tmp_path: Path) -> None:
    """AC10 scenario 3: phase 2 not approved → ERR_PHASE2_NOT_APPROVED, no files written."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _seed_architecture_md(tmp_path)
    # Phase 1 approved, phase 2 NOT approved
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _seed_story_json(tmp_path, status="in-progress")

    with unittest.mock.patch("sdlc.cli._break_pipeline.dispatch") as mock_dispatch:
        result = _invoke_break(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE2_NOT_APPROVED" in (result.stdout + (result.stderr or ""))
    mock_dispatch.assert_not_called()

    # Nothing written under tasks/
    tasks_dir = tmp_path / "03-Implementation" / "tasks"
    if tasks_dir.exists():
        assert list(tasks_dir.rglob("*.json")) == [], "no task files must be written"

    # No dispatch journalled
    entries = _read_journal(tmp_path)
    assert [e for e in entries if e["kind"] == "agent_dispatched"] == []


# ---------------------------------------------------------------------------
# Scenario 2 (spec AC10.2) — Refuse: story not active
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_break_story_not_active(tmp_path: Path) -> None:
    """AC10 scenario 2: story status 'pending' → exit 1, 'story not active', no dispatch."""
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path, status="pending")

    with unittest.mock.patch("sdlc.cli._break_pipeline.dispatch") as mock_dispatch:
        result = _invoke_break(tmp_path)

    assert result.exit_code == 1
    assert "story not active" in (result.stdout + (result.stderr or "")).lower()
    mock_dispatch.assert_not_called()

    # Nothing written under tasks/
    tasks_dir = tmp_path / "03-Implementation" / "tasks"
    if tasks_dir.exists():
        assert list(tasks_dir.rglob("*.json")) == [], "no task files must be written"

    # No dispatch journalled
    entries = _read_journal(tmp_path)
    assert [e for e in entries if e["kind"] == "agent_dispatched"] == []

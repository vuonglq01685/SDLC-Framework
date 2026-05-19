"""Tier-2 e2e for ``sdlc next`` — phase-aware router (Story 2A.18, AC7).

Four scenarios per AC7:
  1. Phase 3 auto-dispatch: phase2 APPROVED + pending dep-satisfied task →
     sdlc next calls run_task; task stage advances; task_stage_advanced journaled.
  2. Phase 2 print: phase1 APPROVED, phase2 unsigned, no arch artifact →
     exit 0, stdout/--json suggests /sdlc-architect, no dispatch occurs.
  3. No ready items: all Phase 3 tasks at stage done →
     exit 0, next_action: "none", reason names fully-advanced state.
  4. Dependency-blocked: task T01-blocked (pending, deps=[T02-ready]) +
     task T02-ready (pending, deps=[]) → resolver selects T02-ready (not T01-blocked),
     because T01-blocked's dependency is unsatisfied.

Anti-tautology receipt (AC7 mandatory):
  ``test_e2e_next_dependency_gate_is_load_bearing``:
  Fixture has T01-blocked (seq=01) depending on T02-ready (seq=02, pending).
  With gate active: T01-blocked is skipped → T02-ready selected (correct).
  With gate neutralised (all deps treated as satisfied): T01-blocked selected
  (seq=01 wins by order) → WRONG result. Confirms the gate, not seq order alone,
  drives the selection.
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

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

_EPIC_ID = "EPIC-enext"
_STORY_ID = f"{_EPIC_ID}-S01-next"
_TASK_READY_ID = f"{_STORY_ID}-T02-ready"  # seq=02; dep-free — correct pick with gate
_TASK_BLOCKED_ID = f"{_STORY_ID}-T01-blocked"  # seq=01; depends on T02-ready — blocked

_TS1 = "2026-05-18T09:00:00.000Z"
_TS2 = "2026-05-18T10:00:00.000Z"

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_product_md(tmp_path: Path) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Product Brief\n\n## Overview\n\nTest product.\n", encoding="utf-8")
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


def _ready_approved_repo(tmp_path: Path) -> Path:
    """Init + phase-1/2 signoffs. Returns PRODUCT.md path."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, product_path, "01-Requirement/01-PRODUCT.md")
    return product_path


def _seed_story_json(tmp_path: Path) -> Path:
    story_dir = tmp_path / "01-Requirement" / "05-Stories" / _EPIC_ID
    story_dir.mkdir(parents=True, exist_ok=True)
    p = story_dir / f"{_STORY_ID}.json"
    data = {
        "schema_version": 1,
        "id": _STORY_ID,
        "epic_id": _EPIC_ID,
        "seq": 1,
        "label": "Next story (e2e)",
        "as_a": "developer",
        "i_want": "next routing",
        "so_that": "workflow advances",
        "given_when_then": ["Given a task, when next runs, then it dispatches."],
        "dependencies": [],
        "drafted_at": _TS1,
        "drafted_by_specialist": "e2e-test",
    }
    p.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    return p


def _write_task(
    tmp_path: Path,
    task_id: str,
    *,
    stage: str = "pending",
    dependencies: list[str] | None = None,
) -> Path:
    parts = task_id.rsplit("-T", maxsplit=1)
    fname = f"T{parts[1]}.json" if len(parts) == 2 else f"{task_id}.json"
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    tasks_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": task_id,
        "story_id": _STORY_ID,
        "label": f"Task {task_id.rsplit('-T', 1)[-1]}",
        "stage": stage,
        "dependencies": dependencies or [],
        "review_verdict": None,
        "review_notes": None,
    }
    p = tasks_dir / fname
    p.write_text(json.dumps(entry, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _invoke_next(tmp_path: Path, *, json_out: bool = False) -> Any:
    args = ["--json", "next"] if json_out else ["next"]
    with (
        unittest.mock.patch("sdlc.cli.next_._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.task._get_repo_root_or_cwd", return_value=tmp_path),
    ):
        return _runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Scenario 1 — Phase 3 auto-dispatch (AC7.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_next_phase3_auto_dispatch(tmp_path: Path) -> None:
    """Phase 2 APPROVED + pending dep-satisfied task → sdlc next dispatches sdlc task.

    Verifies: task stage advances from pending; task_stage_advanced journaled; exit 0.
    Uses real MockAIRuntime pipeline (SDLC_USE_MOCK_RUNTIME=1 default).
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)
    # Single dep-free pending task
    task_path = _write_task(tmp_path, _TASK_READY_ID, stage="pending", dependencies=[])

    r = _invoke_next(tmp_path)

    assert r.exit_code == 0, f"sdlc next failed unexpectedly: {r.output}"

    # Task stage advanced exactly one step: pending → write-tests (one-stage-per-invocation)
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    assert task_data["stage"] == "write-tests", (
        f"task should have advanced pending → write-tests; got stage={task_data['stage']!r}"
    )

    # Journal has at least one task_stage_advanced entry
    entries = _read_journal(tmp_path)
    kinds = [e.get("kind") for e in entries]
    assert "task_stage_advanced" in kinds, (
        f"expected task_stage_advanced in journal; got kinds={kinds}"
    )


# ---------------------------------------------------------------------------
# Scenario 2 — Phase 2 print path (AC7.2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_next_phase2_print_suggests_sdlc_architect(tmp_path: Path) -> None:
    """Phase 1 APPROVED, Phase 2 unsigned, no arch artifact → suggests /sdlc-architect."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    # No Phase 2 signoff, no architecture artifact

    r = _invoke_next(tmp_path, json_out=True)

    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["next_action"] == "command"
    assert "/sdlc-architect" in data["suggested_command"]

    # No dispatch occurred — journal has no task_stage_advanced
    entries = _read_journal(tmp_path)
    kinds = [e.get("kind") for e in entries]
    assert "task_stage_advanced" not in kinds, f"unexpected dispatch; journal kinds={kinds}"


# ---------------------------------------------------------------------------
# Scenario 3 — No ready items (all done) (AC7.3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_next_no_ready_items_all_tasks_done(tmp_path: Path) -> None:
    """All Phase 3 tasks at stage done → next_action: none, reason names fully-advanced state."""
    _ready_approved_repo(tmp_path)
    _write_task(tmp_path, _TASK_READY_ID, stage="done")

    r = _invoke_next(tmp_path, json_out=True)

    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["next_action"] == "none"
    assert "complete" in data["reason"].lower() or "done" in data["reason"].lower()


# ---------------------------------------------------------------------------
# Scenario 4 — Dependency-blocked: resolver selects T02-ready (not T01-blocked) (AC7.4)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_next_dependency_blocked_selects_dep_free_task(tmp_path: Path) -> None:
    """T01-blocked depends on T02-ready (pending) → `sdlc next` dispatches T02-ready.

    T01-blocked (seq=01) would be picked first by pure seq order if no dep gate.
    With dep gate active: T01-blocked is skipped (T02-ready not done); T02-ready
    is dispatched end-to-end through the CLI (AC7 — "invoke `sdlc next`").
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)  # run_task needs the story JSON for STORY_CONTEXT
    blocked_path = _write_task(
        tmp_path, _TASK_BLOCKED_ID, stage="pending", dependencies=[_TASK_READY_ID]
    )
    ready_path = _write_task(tmp_path, _TASK_READY_ID, stage="pending", dependencies=[])

    r = _invoke_next(tmp_path)

    assert r.exit_code == 0, f"sdlc next failed unexpectedly: {r.output}"
    # The dep-free task (T02-ready) is dispatched and advances; the blocked task stays put.
    ready_stage = json.loads(ready_path.read_text(encoding="utf-8"))["stage"]
    blocked_stage = json.loads(blocked_path.read_text(encoding="utf-8"))["stage"]
    assert ready_stage != "pending", (
        f"dep-free {_TASK_READY_ID!r} should have been dispatched; got stage={ready_stage!r}"
    )
    assert blocked_stage == "pending", (
        f"blocked {_TASK_BLOCKED_ID!r} must NOT be dispatched; got stage={blocked_stage!r}"
    )


# ---------------------------------------------------------------------------
# Anti-tautology receipt (AC7 mandatory)
# test_e2e_next_dependency_gate_is_load_bearing
# ---------------------------------------------------------------------------


def _select_no_dep_check(tasks_root: Path) -> tuple[object, dict]:
    """Neutralised gate: pick first non-done task by seq with no dep check."""
    from sdlc.cli._epic_story_models import _TaskEntry
    from sdlc.cli._next_resolver import _parse_story_seq, _parse_task_seq

    if not tasks_root.is_dir():
        return None, {}
    candidates: list[tuple[int, int, _TaskEntry]] = []
    for story_dir in sorted(tasks_root.iterdir()):
        if not story_dir.is_dir():
            continue
        for task_path in sorted(story_dir.glob("T*-*.json")):
            try:
                task = _TaskEntry.model_validate_json(task_path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if task.stage != "done":
                candidates.append(
                    (_parse_story_seq(story_dir.name), _parse_task_seq(task.id), task)
                )
    if not candidates:
        return None, {}
    candidates.sort()
    return candidates[0][2], {}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_next_dependency_gate_is_load_bearing(tmp_path: Path) -> None:
    """Prove the dependency gate, not seq order alone, drives task selection.

    Fixture: T01-blocked (seq=01, deps=[T02-ready]) + T02-ready (seq=02, deps=[]).
    - Gate active:     `sdlc next` dispatches T02-ready, T01-blocked stays pending (CORRECT).
    - Gate neutralised: `sdlc next` dispatches T01-blocked (seq=01 wins by order) → WRONG.

    Both arms invoke `sdlc next` end-to-end (AC7). Documented in PR Change Log as
    'test_e2e_next_dependency_gate_is_load_bearing'.
    """
    _ready_approved_repo(tmp_path)
    _seed_story_json(tmp_path)  # run_task needs the story JSON for STORY_CONTEXT
    blocked_path = _write_task(
        tmp_path, _TASK_BLOCKED_ID, stage="pending", dependencies=[_TASK_READY_ID]
    )
    ready_path = _write_task(tmp_path, _TASK_READY_ID, stage="pending", dependencies=[])

    from sdlc.cli import _next_resolver as resolver_mod

    # --- Gate active: `sdlc next` dispatches the dep-free T02-ready ---
    r_gate = _invoke_next(tmp_path)
    assert r_gate.exit_code == 0, f"sdlc next failed unexpectedly: {r_gate.output}"
    assert json.loads(ready_path.read_text(encoding="utf-8"))["stage"] != "pending", (
        "gate active: T02-ready (dep-free) should have been dispatched"
    )
    assert json.loads(blocked_path.read_text(encoding="utf-8"))["stage"] == "pending", (
        "gate active: T01-blocked must NOT be dispatched"
    )

    # --- Reset task files, then neutralise the gate ---
    blocked_path = _write_task(
        tmp_path, _TASK_BLOCKED_ID, stage="pending", dependencies=[_TASK_READY_ID]
    )
    ready_path = _write_task(tmp_path, _TASK_READY_ID, stage="pending", dependencies=[])

    with unittest.mock.patch.object(
        resolver_mod, "_select_phase3_task", side_effect=_select_no_dep_check
    ):
        r_no_gate = _invoke_next(tmp_path)

    assert r_no_gate.exit_code == 0, f"sdlc next failed unexpectedly: {r_no_gate.output}"
    # Gate neutralised: T01-blocked (seq=01) wrongly wins by order and is dispatched.
    assert json.loads(blocked_path.read_text(encoding="utf-8"))["stage"] != "pending", (
        "gate neutralised: T01-blocked (seq=01) wrongly dispatched — proves gate is load-bearing"
    )

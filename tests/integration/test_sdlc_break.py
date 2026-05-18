"""Integration tests for ``sdlc break`` (Story 2A.16, AC1-AC6, Task 4.4)."""

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

_STORY_ID = "EPIC-testprod-S01-user-auth"
_EPIC_ID = "EPIC-testprod"

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


def _write_product_md(tmp_path: Path) -> Path:
    p = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Product Brief\n\nA product for integration testing.\n", encoding="utf-8")
    return p


def _write_architecture_md(tmp_path: Path) -> Path:
    p = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# System Architecture\n\nMinimal stub for testing.\n", encoding="utf-8")
    return p


def _write_story_json(
    tmp_path: Path, story_id: str = _STORY_ID, status: str = "in-progress"
) -> Path:
    parsed_story_num = int(story_id.split("-S")[1].split("-", maxsplit=1)[0])
    epic_slug = story_id.split("-S", maxsplit=1)[0][len("EPIC-") :]
    epic_id = f"EPIC-{epic_slug}"

    story_data = {
        "schema_version": 1,
        "id": story_id,
        "epic_id": epic_id,
        "seq": parsed_story_num,
        "label": f"Story {story_id} for integration test",
        "as_a": "developer",
        "i_want": "to implement user authentication",
        "so_that": "users can log in securely",
        "given_when_then": [
            "Given the auth service is up, when a user logs in, then a token is returned."
        ],
        "dependencies": [],
        "drafted_at": "2026-05-18T09:00:00Z",
        "drafted_by_specialist": "test-specialist",
        "status": status,
    }
    p = tmp_path / "01-Requirement" / "05-Stories" / epic_id / f"{story_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(story_data, sort_keys=True, indent=2), encoding="utf-8")
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


def _read_journal(tmp_path: Path) -> list[dict[str, object]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _invoke_break(tmp_path: Path, story_id: str = _STORY_ID, *, json_mode: bool = True) -> object:
    args = ["--json", "break", story_id] if json_mode else ["break", story_id]
    with unittest.mock.patch("sdlc.cli.break_._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Happy path: full MockAIRuntime pipeline (no dispatch mock)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_break_integration_full_pipeline(tmp_path: Path) -> None:
    """AC1/AC4/AC5/AC6: full pipeline — 3 task files, journal sequence, emit_json success."""
    _init_repo(tmp_path)
    product_path = _write_product_md(tmp_path)
    arch_path = _write_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")
    _write_story_json(tmp_path, story_id=_STORY_ID, status="in-progress")

    result = _invoke_break(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: 3 task files written at correct paths
    tasks_dir = tmp_path / "03-Implementation" / "tasks" / _STORY_ID
    assert tasks_dir.is_dir(), f"tasks dir not created: {tasks_dir}"
    task_files = sorted(tasks_dir.glob("T*-*.json"))
    assert len(task_files) == 3, f"expected 3 task files; got {[f.name for f in task_files]}"

    # task files are readable and have expected fields
    for f in task_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["story_id"] == _STORY_ID
        assert data["stage"] == "pending"
        assert data["id"].startswith(_STORY_ID)

    # sequential numbering T01, T02, T03
    assert task_files[0].name.startswith("T01-")
    assert task_files[1].name.startswith("T02-")
    assert task_files[2].name.startswith("T03-")

    # AC6: journal sequence - agent_dispatched -> 3x artifact_written -> story_broken_into_tasks
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    broken = [e for e in entries if e["kind"] == "story_broken_into_tasks"]

    assert any(e["payload"].get("specialist") == "task-breaker" for e in dispatched), (
        "journal must have agent_dispatched for task-breaker"
    )
    assert len(written) == 3, f"expected 3 artifact_written entries; got {len(written)}"
    for e in written:
        assert e["actor"] == "cli"
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 3
        assert _STORY_ID in e["payload"]["target"]

    assert len(broken) == 1, (
        f"expected exactly one story_broken_into_tasks entry; got {len(broken)}"
    )
    bt = broken[0]
    assert bt["payload"]["story_id"] == _STORY_ID
    assert bt["payload"]["task_count"] == 3
    assert len(bt["payload"]["task_ids"]) == 3

    # Sequence ordering
    dispatch_seqs = [
        e["monotonic_seq"] for e in dispatched if e["payload"].get("specialist") == "task-breaker"
    ]
    written_seqs = [e["monotonic_seq"] for e in written]
    broken_seq = bt["monotonic_seq"]
    assert dispatch_seqs
    assert max(dispatch_seqs) < min(written_seqs), "dispatched must precede written"
    assert max(written_seqs) < broken_seq, "written must precede story_broken_into_tasks"

    # AC6: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 3
    assert out["track"] == "break"
    assert out["specialist"] == "task-breaker"
    assert out["story_id"] == _STORY_ID
    assert out["task_count"] == 3
    assert out["outcome"] == "success"
    assert len(out["task_ids"]) == 3
    assert out["task_count"] == bt["payload"]["task_count"]

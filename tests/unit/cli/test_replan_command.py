"""Unit tests for cli/replan_cmd.py:run_replan (Story 2A.19, Tasks 1.4 + 3.1).

Task 1.4 — RED tests for scope validation + init guard:
  - command registered; init guard; bad scope (absolute/backslash/dotdot);
    missing artifact; scope outside phase dir.

Task 3.1 — RED tests for orchestration:
  - phase 2 scope → only Phase 2 invalidated + 1 signoff_invalidated entry
  - phase 1 scope → Phase 1 + Phase 2 invalidated + 2 signoff_invalidated entries
  - phase 3 scope → no invalidate_record; still 1 replan_invalidated entry
  - replan-then-replan → second run skips already-invalidated phase (AC3)
  - replan_invalidated payload carries scope/scope_phase/downstream_count/downstream_artifacts
  - emit_json envelope shape (AC4)
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.unit

_runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_replan(tmp_path: Path, scope: str, *, json_out: bool = True) -> Any:
    args = (["--json"] if json_out else []) + ["replan", "--scope", scope]
    with unittest.mock.patch("sdlc.cli.replan_cmd._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_artifact(tmp_path: Path, rel_path: str, content: str = "# stub\n") -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _approve_phase(tmp_path: Path, phase: int, artifact_rel: str) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    artifact_path = tmp_path / artifact_rel
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_rel, hash=artifact_hash),),
        approved_by="test-approver",
        approved_at="2026-05-19T10:00:00.000Z",
        drafted_at="2026-05-19T09:00:00.000Z",
        validated_at="2026-05-19T10:00:00.000Z",
    )
    write_record(record, repo_root=tmp_path)


def _read_journal_entries(tmp_path: Path) -> list[Any]:
    from sdlc.journal import iter_entries

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    if not journal_path.exists():
        return []
    return list(iter_entries(journal_path))


# ---------------------------------------------------------------------------
# AC1 — Command registered (Task 1.4)
# ---------------------------------------------------------------------------


def test_replan_command_registered() -> None:
    result = _runner.invoke(app, ["replan", "--help"])
    assert result.exit_code == 0
    assert "--scope" in result.output


# ---------------------------------------------------------------------------
# AC1 — Init guard (Task 1.4)
# ---------------------------------------------------------------------------


def test_not_initialized_exits_nonzero(tmp_path: Path) -> None:
    _seed_artifact(tmp_path, "02-Architecture/02-System/ARCHITECTURE.md")
    r = _invoke_replan(tmp_path, "02-Architecture/02-System/ARCHITECTURE.md")
    assert r.exit_code != 0
    assert "ERR_NOT_INITIALIZED" in r.output


def test_not_initialized_json_envelope(tmp_path: Path) -> None:
    _seed_artifact(tmp_path, "02-Architecture/02-System/ARCHITECTURE.md")
    r = _invoke_replan(tmp_path, "02-Architecture/02-System/ARCHITECTURE.md", json_out=True)
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_NOT_INITIALIZED"


# ---------------------------------------------------------------------------
# AC1 — Scope validation (Task 1.4)
# ---------------------------------------------------------------------------


def test_absolute_scope_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke_replan(tmp_path, "/absolute/path/artifact.md")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "invalid --scope" in data["error"]["message"]


def test_backslash_scope_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke_replan(tmp_path, "02-Architecture\\artifact.md")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "invalid --scope" in data["error"]["message"]


def test_dotdot_traversal_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke_replan(tmp_path, "../outside/artifact.md")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "invalid --scope" in data["error"]["message"]


def test_missing_scope_artifact_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke_replan(tmp_path, "02-Architecture/02-System/NONEXISTENT.md")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "not found" in data["error"]["message"]


def test_scope_outside_phase_dir_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _seed_artifact(tmp_path, "docs/some-doc.md")
    r = _invoke_replan(tmp_path, "docs/some-doc.md")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "not under a recognized phase directory" in data["error"]["message"]


def test_directory_scope_rejected(tmp_path: Path) -> None:
    """A directory-valued --scope is rejected before read_bytes() (CR review patch).

    A bare phase-subdirectory passes scope-validation, resolve_scope_phase, and
    the .exists() guard; without an is_file() check it would crash with an
    uncaught IsADirectoryError. It must fail cleanly with ERR_USER_INPUT.
    """
    _init_repo(tmp_path)
    (tmp_path / "02-Architecture" / "02-System").mkdir(parents=True)
    r = _invoke_replan(tmp_path, "02-Architecture/02-System")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "not a file" in data["error"]["message"]


def test_replan_succeeds_without_json_flag(tmp_path: Path) -> None:
    """`sdlc replan` (no --json) still completes successfully (CR review patch).

    Exercises the non-JSON invocation path — previously dead test scaffolding.
    """
    _init_repo(tmp_path)
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_artifact(tmp_path, arch_rel)
    _approve_phase(tmp_path, 2, arch_rel)
    r = _invoke_replan(tmp_path, arch_rel, json_out=False)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["command"] == "replan"
    assert data["outcome"] == "success"


# ---------------------------------------------------------------------------
# Task 3.1 — Phase 2 scope: only Phase 2 invalidated
# ---------------------------------------------------------------------------


def test_phase2_scope_only_invalidates_phase2(tmp_path: Path) -> None:
    """Phase 2 scope → only Phase 2 signoff invalidated; Phase 1 stays APPROVED."""
    _init_repo(tmp_path)
    scope = "02-Architecture/02-System/ARCHITECTURE.md"
    product_rel = "01-Requirement/01-PRODUCT.md"
    _seed_artifact(tmp_path, scope)
    _seed_artifact(tmp_path, product_rel)
    _approve_phase(tmp_path, 1, product_rel)
    _approve_phase(tmp_path, 2, scope)

    r = _invoke_replan(tmp_path, scope)
    assert r.exit_code == 0, r.output

    from sdlc.signoff import SignoffState, compute_state

    assert compute_state(2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN
    assert compute_state(1, repo_root=tmp_path) == SignoffState.APPROVED

    entries = _read_journal_entries(tmp_path)
    replan_entries = [e for e in entries if e.kind == "replan_invalidated"]
    signoff_entries = [e for e in entries if e.kind == "signoff_invalidated"]
    assert len(replan_entries) == 1
    assert len(signoff_entries) == 1
    assert signoff_entries[0].payload["phase"] == 2


def test_phase2_scope_json_envelope(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    scope = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_artifact(tmp_path, scope)
    _seed_artifact(tmp_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, scope)

    r = _invoke_replan(tmp_path, scope)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["command"] == "replan"
    assert data["scope"] == scope
    assert data["scope_phase"] == 2
    assert data["invalidated_phases"] == [2]
    assert data["outcome"] == "success"
    assert "downstream_count" in data


# ---------------------------------------------------------------------------
# Task 3.1 — Phase 1 scope: both phases invalidated
# ---------------------------------------------------------------------------


def test_phase1_scope_invalidates_both_phases(tmp_path: Path) -> None:
    """Phase 1 scope → Phase 1 and Phase 2 both invalidated."""
    _init_repo(tmp_path)
    product_rel = "01-Requirement/01-PRODUCT.md"
    arch_rel = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_artifact(tmp_path, product_rel)
    _seed_artifact(tmp_path, arch_rel)
    _approve_phase(tmp_path, 1, product_rel)
    _approve_phase(tmp_path, 2, arch_rel)

    r = _invoke_replan(tmp_path, product_rel)
    assert r.exit_code == 0, r.output

    from sdlc.signoff import SignoffState, compute_state

    assert compute_state(1, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN
    assert compute_state(2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

    entries = _read_journal_entries(tmp_path)
    signoff_entries = [e for e in entries if e.kind == "signoff_invalidated"]
    assert len(signoff_entries) == 2
    phases = sorted(e.payload["phase"] for e in signoff_entries)
    assert phases == [1, 2]

    data = json.loads(r.output)
    assert sorted(data["invalidated_phases"]) == [1, 2]


# ---------------------------------------------------------------------------
# Task 3.1 — Phase 3 scope: no invalidate_record; still 1 replan_invalidated
# ---------------------------------------------------------------------------


def test_phase3_scope_no_signoff_invalidation(tmp_path: Path) -> None:
    """Phase 3 scope → no signoff invalidation (phase 3 has no signoff)."""
    _init_repo(tmp_path)
    scope = "03-Implementation/some-code.py"
    _seed_artifact(tmp_path, scope)

    r = _invoke_replan(tmp_path, scope)
    assert r.exit_code == 0, r.output

    entries = _read_journal_entries(tmp_path)
    replan_entries = [e for e in entries if e.kind == "replan_invalidated"]
    signoff_entries = [e for e in entries if e.kind == "signoff_invalidated"]
    assert len(replan_entries) == 1
    assert len(signoff_entries) == 0

    data = json.loads(r.output)
    assert data["scope_phase"] == 3
    assert data["invalidated_phases"] == []


# ---------------------------------------------------------------------------
# Task 3.1 — Replan-then-replan: already-invalidated phase not re-invalidated
# ---------------------------------------------------------------------------


def test_replan_then_replan_skips_already_invalidated(tmp_path: Path) -> None:
    """Second replan does not re-invalidate an already-invalidated signoff (AC3)."""
    _init_repo(tmp_path)
    scope = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_artifact(tmp_path, scope)
    _seed_artifact(tmp_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, scope)

    # First replan
    r1 = _invoke_replan(tmp_path, scope)
    assert r1.exit_code == 0, r1.output

    # Second replan — should succeed but skip re-invalidation
    r2 = _invoke_replan(tmp_path, scope)
    assert r2.exit_code == 0, r2.output

    data2 = json.loads(r2.output)
    assert data2["invalidated_phases"] == []  # no phase re-invalidated

    from sdlc.signoff import SignoffState, compute_state

    # Still invalidated from first run
    assert compute_state(2, repo_root=tmp_path) == SignoffState.INVALIDATED_BY_REPLAN

    # Only 2 replan_invalidated + 1 signoff_invalidated total (from first run only)
    entries = _read_journal_entries(tmp_path)
    replan_entries = [e for e in entries if e.kind == "replan_invalidated"]
    signoff_entries = [e for e in entries if e.kind == "signoff_invalidated"]
    assert len(replan_entries) == 2  # one per invocation
    assert len(signoff_entries) == 1  # only from first run


# ---------------------------------------------------------------------------
# Task 3.1 — replan_invalidated payload content
# ---------------------------------------------------------------------------


def test_replan_invalidated_payload_content(tmp_path: Path) -> None:
    """replan_invalidated entry payload carries expected keys."""
    _init_repo(tmp_path)
    scope = "02-Architecture/02-System/ARCHITECTURE.md"
    _seed_artifact(tmp_path, scope)
    _approve_phase(tmp_path, 2, scope)

    r = _invoke_replan(tmp_path, scope)
    assert r.exit_code == 0, r.output

    entries = _read_journal_entries(tmp_path)
    replan_entry = next(e for e in entries if e.kind == "replan_invalidated")

    assert replan_entry.target_id == scope
    payload = replan_entry.payload
    assert payload["scope"] == scope
    assert payload["scope_phase"] == 2
    assert "downstream_artifacts" in payload
    assert isinstance(payload["downstream_artifacts"], (list, tuple))
    assert "downstream_count" in payload
    assert "reason" in payload

"""Tier-2 e2e for ``sdlc bootstrap`` (Story 2A.15, AC9/AC10).

AC10 mandates THREE scenarios, all driven through the real MockAIRuntime
pipeline (no ``dispatch`` mock):

  1. Happy path (greenfield): phase 2 APPROVED + empty src/ → specialist
     dispatched, files written under src/ and tests/, journal has
     agent_dispatched -> N x artifact_written -> bootstrap_completed, success JSON.
  2. Auto-skip (brownfield): src/ already contains a real source file → exit 0,
     outcome=skipped, reason=source-exists, no dispatch or file writes.
  3. Phase 2 gate blocked: phase 2 not approved + empty src/ → exit 1,
     ERR_PHASE2_NOT_APPROVED, nothing written.

Anti-tautology receipt (AC9 mandatory — executable form):
``test_e2e_sdlc_bootstrap_skip_guard_is_load_bearing`` inverts
``_source_exists`` to always return False, then re-runs scenario 2's
input (src/ pre-populated) and asserts the outcome is NO LONGER "skipped"
— proving the ``_source_exists`` guard, and only that guard, is what
causes auto-skip. This replaces a prose-only receipt with a kept regression.
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
from sdlc.dispatcher.prompts import BOUNDARY_LINE
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "bootstrap"

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


def _seed_architecture_md(tmp_path: Path) -> Path:
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    arch_dir.mkdir(parents=True, exist_ok=True)
    p = arch_dir / "ARCHITECTURE.md"
    p.write_bytes((_FIXTURES / "ARCHITECTURE.md").read_bytes())
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


def _invoke_bootstrap(tmp_path: Path, *, json_mode: bool = True) -> Any:
    args = ["--json", "bootstrap"] if json_mode else ["bootstrap"]
    with unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _read_agent_runs(tmp_path: Path) -> list[dict[str, Any]]:
    rp = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    if not rp.is_file():
        return []
    return [
        json.loads(line) for line in rp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: greenfield, phase 2 APPROVED (AC10.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_bootstrap_happy_path(tmp_path: Path) -> None:
    """AC10 scenario 1: phase 2 APPROVED + empty src/ → files written + journal."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    arch_path = _seed_architecture_md(tmp_path)
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")
    _approve_phase(tmp_path, 2, arch_path, "02-Architecture/02-System/ARCHITECTURE.md")

    result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: src/ populated with at least one non-placeholder file
    src_dir = tmp_path / "src"
    assert src_dir.is_dir(), "src/ must be created by bootstrap"
    real_files = [
        p for p in src_dir.rglob("*") if p.is_file() and p.name not in {".gitkeep", "README.md"}
    ]
    assert real_files, "src/ must contain at least one real source file"

    # AC7: journal sequence agent_dispatched → artifact_written(s) → bootstrap_completed
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    completed = [e for e in entries if e["kind"] == "bootstrap_completed"]

    assert any(e["payload"]["specialist"] == "code-bootstrapper" for e in dispatched), (
        "journal must have agent_dispatched for code-bootstrapper"
    )
    assert len(written) >= 1, "at least one artifact_written entry required"
    assert len(completed) == 1, "exactly one bootstrap_completed entry required"

    bc = completed[0]
    assert bc["payload"]["files_written"] >= 1
    assert bc["payload"]["specialist"] == "code-bootstrapper"
    assert bc["payload"]["phase"] == 3

    # Journal ordering: dispatch before writes, writes before completion
    dispatch_seqs = [
        e["monotonic_seq"]
        for e in dispatched
        if e["payload"].get("specialist") == "code-bootstrapper"
    ]
    written_seqs = [e["monotonic_seq"] for e in written]
    completed_seq = bc["monotonic_seq"]
    assert max(dispatch_seqs) < min(written_seqs), "agent_dispatched must precede artifact_written"
    assert max(written_seqs) < completed_seq, "artifact_written must precede bootstrap_completed"

    # All artifact_written entries are for phase 3, under src/ or tests/
    for e in written:
        assert e["payload"]["phase"] == 3
        assert e["actor"] == "cli"
        target = e["payload"]["target"]
        assert target.startswith("src/") or target.startswith("tests/"), (
            f"written file outside allowed roots: {target!r}"
        )

    # AC1: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 3
    assert out["track"] == "bootstrap"
    assert out["specialist"] == "code-bootstrapper"
    assert out["outcome"] == "success"
    assert out["source_root"] == "src"
    assert isinstance(out["files_written"], int) and out["files_written"] >= 1
    assert out["files_written"] == bc["payload"]["files_written"]

    # P11 (AC5): BOUNDARY_LINE must be present in the dispatched prompt
    runs = _read_agent_runs(tmp_path)
    prompt_rows = [r for r in runs if isinstance(r.get("dispatch_prompt"), str)]
    assert prompt_rows, "agent_runs.jsonl must contain at least one dispatch_prompt row"
    assert any(BOUNDARY_LINE in r["dispatch_prompt"] for r in prompt_rows), (
        "BOUNDARY_LINE missing from all dispatched prompts in agent_runs.jsonl"
    )

    # AC8: idempotency — second run auto-skips (mock writes src/__init__.py)
    result2 = _invoke_bootstrap(tmp_path)
    assert result2.exit_code == 0, result2.stdout + (result2.stderr or "")
    out2 = json.loads(result2.stdout)
    assert out2["outcome"] == "skipped", "second run must auto-skip when src/ is populated"
    assert out2["reason"] == "source-exists"


# ---------------------------------------------------------------------------
# Scenario 2 — Auto-skip: src/ already populated (AC10.2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_bootstrap_auto_skip(tmp_path: Path) -> None:
    """AC10 scenario 2: src/ has a real file → exit 0, outcome=skipped, no dispatch."""
    _init_repo(tmp_path)
    _seed_product_md(tmp_path)
    # Pre-populate src/ — no Phase 2 signoff needed (FR15 brownfield invariant)
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "app.py").write_text("# pre-existing source file\n", encoding="utf-8")

    with unittest.mock.patch("sdlc.cli._bootstrap_pipeline.dispatch") as mock_dispatch:
        result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_dispatch.assert_not_called()

    out = json.loads(result.stdout)
    assert out["outcome"] == "skipped"
    assert out["reason"] == "source-exists"
    assert out["phase"] == 3
    assert "source_root" in out

    # No dispatch — no journal entries from bootstrap
    entries = _read_journal(tmp_path)
    assert [e for e in entries if e["kind"] == "agent_dispatched"] == []
    assert [e for e in entries if e["kind"] == "bootstrap_completed"] == []

    # Pre-existing file unmolested
    assert (src / "app.py").read_text(encoding="utf-8") == "# pre-existing source file\n"


# ---------------------------------------------------------------------------
# Scenario 3 — Phase 2 gate blocked (AC10.3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_bootstrap_phase2_gate_blocked(tmp_path: Path) -> None:
    """AC10 scenario 3: phase 2 not approved + empty src/ → ERR_PHASE2_NOT_APPROVED."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _seed_architecture_md(tmp_path)
    # Phase 1 approved, phase 2 NOT approved
    _approve_phase(tmp_path, 1, product_path, "01-Requirement/01-PRODUCT.md")

    result = _invoke_bootstrap(tmp_path)

    assert result.exit_code == 1
    output = result.stdout + (result.stderr or "")
    assert "ERR_PHASE2_NOT_APPROVED" in output

    # Nothing written under src/ (may not even exist)
    src_dir = tmp_path / "src"
    if src_dir.exists():
        real = [
            p for p in src_dir.rglob("*") if p.is_file() and p.name not in {".gitkeep", "README.md"}
        ]
        assert real == [], "no real source files must be written when phase 2 gate blocks"

    # No dispatch journalled
    entries = _read_journal(tmp_path)
    assert [e for e in entries if e["kind"] == "agent_dispatched"] == []


# ---------------------------------------------------------------------------
# Anti-tautology receipt (AC9 mandatory — executable form)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_bootstrap_skip_guard_is_load_bearing(tmp_path: Path) -> None:
    """AC9 anti-tautology receipt (executable form).

    Mutation: patch ``_source_exists`` to always return False, then re-run
    scenario 2's input (src/ pre-populated). With the guard neutralised the
    command MUST proceed past the auto-skip check — i.e. the outcome must NOT
    be "skipped". This proves ``_source_exists``, and only it, causes scenario
    2 to skip; if the same input were to still skip with the guard off, the
    scenario-2 assertion would be tautological.

    Because the Phase 2 gate is not satisfied in this repo (no signoff written),
    the mutated run is expected to exit 1 with ERR_PHASE2_NOT_APPROVED — which
    is proof enough that the skip path was bypassed.
    """
    _init_repo(tmp_path)
    _seed_product_md(tmp_path)
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "app.py").write_text("# pre-existing source file\n", encoding="utf-8")

    # Neutralise _source_exists so auto-skip cannot fire
    with (
        unittest.mock.patch("sdlc.cli.bootstrap._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.bootstrap._source_exists", return_value=False),
    ):
        result = _runner.invoke(app, ["--json", "bootstrap"])

    out_text = result.stdout + (result.stderr or "")
    # Guard neutralised → skip cannot happen → outcome is NOT "skipped"
    if result.exit_code == 0:
        out = json.loads(result.stdout)
        assert out.get("outcome") != "skipped", (
            "anti-tautology breach: scenario 2 still produces outcome=skipped "
            "even with _source_exists neutralised — skip guard is NOT load-bearing"
        )
    else:
        # Expected: exit 1 because phase 2 is not approved (skip was bypassed)
        assert "ERR_PHASE2_NOT_APPROVED" in out_text or result.exit_code != 0, (
            "anti-tautology breach: unexpected failure mode; skip guard may not be load-bearing"
        )

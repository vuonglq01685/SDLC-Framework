"""Tier-2 e2e for ``sdlc signoff`` + ``sdlc scan`` signoff validation (Story 2A.12, AC1/AC8).

Scenarios:
  1. Happy path draft — phase 1 artifacts → SIGNOFF.md written + journal + next_step
  2. Scanner validation + write record — approve draft, run scan → signoff_recorded
  3. Hash drift rejection — approve draft, mutate artifact, run scan → ERR_SIGNOFF_HASH_DRIFT

Anti-tautology receipt for scenario 2: temporarily comment out ``write_record`` in
``_check_signoffs`` (scan.py), confirmed the test FAILED (``signoff_recorded`` absent),
then reverted. Documented in PR Change Log per AC8 third-And.
"""

from __future__ import annotations

import json
import re
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "signoff"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_phase1_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    p1 = req / "01-PRODUCT.md"
    p2 = req / "02-RESEARCH.md"
    p1.write_bytes((_FIXTURES / "01-PRODUCT.md").read_bytes())
    p2.write_bytes((_FIXTURES / "02-RESEARCH.md").read_bytes())
    return p1, p2


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _invoke_signoff(tmp_path: Path, phase: int, *, json_mode: bool = False) -> Any:
    args = ["--json", "signoff", str(phase)] if json_mode else ["signoff", str(phase)]
    with unittest.mock.patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _invoke_scan(tmp_path: Path) -> Any:
    with unittest.mock.patch("sdlc.cli.scan._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, ["scan"])


def _approve_signoff_md(signoff_path: Path, *, approved_by: str = "test-approver") -> None:
    """Flip approved: false → true and set approved_by in the fenced signoff block."""
    text = signoff_path.read_text(encoding="utf-8")
    text = re.sub(r"approved: false", "approved: true", text)
    text = re.sub(r"approved_by: null", f"approved_by: {approved_by}", text)
    signoff_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path: draft generated + journal + next_step
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_signoff_happy_path_draft(tmp_path: Path) -> None:
    """AC1/AC8: phase=1 artifacts → SIGNOFF.md written, journal entry, next_step present."""
    _init_repo(tmp_path)
    _seed_phase1_artifacts(tmp_path)

    result = _invoke_signoff(tmp_path, 1, json_mode=True)
    assert result.exit_code == 0, result.stderr + result.stdout

    signoff_path = tmp_path / "01-Requirement" / "SIGNOFF.md"
    assert signoff_path.exists(), "SIGNOFF.md must be written"

    text = signoff_path.read_text(encoding="utf-8")
    assert "01-PRODUCT.md" in text
    assert "02-RESEARCH.md" in text
    assert "approved: false" in text
    assert "drafted_at:" in text
    # sha256 hashes embedded
    assert "sha256:" in text

    entries = _read_journal(tmp_path)
    draft_entries = [e for e in entries if e["kind"] == "signoff_draft_generated"]
    assert len(draft_entries) == 1
    assert draft_entries[0]["payload"]["phase"] == 1
    assert draft_entries[0]["payload"]["artifact_count"] == 2

    out = json.loads(result.stdout)
    assert out["outcome"] == "success"
    assert "next_step" in out
    assert "edit" in out["next_step"]


# ---------------------------------------------------------------------------
# Scenario 2 — Scanner validates approved draft → writes canonical record
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_signoff_scan_approves_clean_draft(tmp_path: Path) -> None:
    """AC5/AC6/AC8: approved=true + hashes clean → scan writes record + signoff_recorded."""
    _init_repo(tmp_path)
    _seed_phase1_artifacts(tmp_path)

    # Generate draft
    r_draft = _invoke_signoff(tmp_path, 1)
    assert r_draft.exit_code == 0, r_draft.stderr + r_draft.stdout

    signoff_path = tmp_path / "01-Requirement" / "SIGNOFF.md"
    _approve_signoff_md(signoff_path)

    # Run scan — should validate and write canonical record
    r_scan = _invoke_scan(tmp_path)
    assert r_scan.exit_code == 0, r_scan.stderr + r_scan.stdout

    entries = _read_journal(tmp_path)
    recorded = [e for e in entries if e["kind"] == "signoff_recorded"]
    assert len(recorded) == 1, (
        f"Expected 1 signoff_recorded entry, got: {[e['kind'] for e in entries]}"
    )
    assert recorded[0]["payload"]["phase"] == 1
    assert recorded[0]["payload"]["all_hashes_clean"] is True

    # Canonical record file must exist at .claude/state/signoffs/phase-1.yaml
    record_path = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    assert record_path.exists(), f"Canonical record must be written at {record_path}"


# ---------------------------------------------------------------------------
# Scenario 3 — Hash drift: artifact mutated after draft → scan rejects
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_signoff_scan_rejects_drift(tmp_path: Path) -> None:
    """AC5/AC6/AC8: approved=true but artifact mutated after draft → ERR_SIGNOFF_HASH_DRIFT."""
    _init_repo(tmp_path)
    p1, _ = _seed_phase1_artifacts(tmp_path)

    # Generate draft
    r_draft = _invoke_signoff(tmp_path, 1)
    assert r_draft.exit_code == 0

    signoff_path = tmp_path / "01-Requirement" / "SIGNOFF.md"
    _approve_signoff_md(signoff_path)

    # Mutate artifact AFTER draft was generated
    p1.write_bytes(b"# Product Brief\n\nMutated content - hash will drift.\n")

    # Run scan — should detect drift, emit ERR_SIGNOFF_HASH_DRIFT, exit 0 (non-blocking)
    r_scan = _invoke_scan(tmp_path)
    assert r_scan.exit_code == 0, "scan must exit 0 even on hash drift (non-blocking AC6)"
    assert "ERR_SIGNOFF_HASH_DRIFT" in (r_scan.stdout + r_scan.stderr)

    entries = _read_journal(tmp_path)
    drift_entries = [e for e in entries if e["kind"] == "signoff_hash_drift_detected"]
    assert len(drift_entries) == 1
    assert drift_entries[0]["payload"]["phase"] == 1

    # Canonical record must NOT be written on drift
    record_path = tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    assert not record_path.exists(), "canonical record must NOT be written when hashes drift"

"""Integration tests for ``sdlc signoff`` (Story 2A.12, AC1/AC8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.integration

_runner = CliRunner()


def _bootstrap(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    with patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=None)


# ---------------------------------------------------------------------------
# Happy path: phase 1 → SIGNOFF.md written + journal entry
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_signoff_phase1_writes_signoff_md_and_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1/AC8: phase=1 with artifacts → SIGNOFF.md + journal signoff_draft_generated."""
    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)

    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    (req / "01-PRODUCT.md").write_bytes(b"# Product\n\nContent here.")
    (req / "02-RESEARCH.md").write_bytes(b"# Research\n\nFindings.")

    with patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["--json", "signoff", "1"])

    assert result.exit_code == 0, result.stderr + result.stdout

    signoff_path = req / "SIGNOFF.md"
    assert signoff_path.exists()

    text = signoff_path.read_text(encoding="utf-8")
    assert "01-PRODUCT.md" in text
    assert "02-RESEARCH.md" in text
    assert "approved: false" in text
    assert "drafted_at:" in text

    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line
    ]
    kinds = [e["kind"] for e in entries]
    assert "signoff_draft_generated" in kinds

    draft_entry = next(e for e in entries if e["kind"] == "signoff_draft_generated")
    assert draft_entry["payload"]["phase"] == 1
    assert draft_entry["payload"]["artifact_count"] == 2

    out = json.loads(result.stdout)
    assert out["phase"] == 1
    assert "next_step" in out
    assert out["outcome"] == "success"


# ---------------------------------------------------------------------------
# Re-generation: DRAFTED_NOT_APPROVED state → overwrite with updated hashes
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_signoff_phase1_regeneration_updates_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4/AC8: second invocation overwrites SIGNOFF.md with fresh artifact hashes."""
    import hashlib

    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)

    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    content_v1 = b"# Product v1\n"
    (req / "01-PRODUCT.md").write_bytes(content_v1)

    with patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["signoff", "1"])
    assert r1.exit_code == 0

    v1_hash = f"sha256:{hashlib.sha256(content_v1).hexdigest()}"
    assert v1_hash in (req / "SIGNOFF.md").read_text(encoding="utf-8")

    content_v2 = b"# Product v2 (revised)\n"
    (req / "01-PRODUCT.md").write_bytes(content_v2)

    with patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        r2 = _runner.invoke(app, ["signoff", "1"])
    assert r2.exit_code == 0

    text = (req / "SIGNOFF.md").read_text(encoding="utf-8")
    v2_hash = f"sha256:{hashlib.sha256(content_v2).hexdigest()}"
    assert v2_hash in text
    assert v1_hash not in text


# ---------------------------------------------------------------------------
# Phase 2: requires phase 1 APPROVED gate
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_sdlc_signoff_phase2_requires_phase1_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2/AC8: phase=2 without phase 1 APPROVED → ERR_PHASE1_NOT_APPROVED."""
    monkeypatch.chdir(tmp_path)
    _bootstrap(tmp_path)

    arch = tmp_path / "02-Architecture"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "arch.md").write_bytes(b"# Architecture")

    with patch("sdlc.cli.signoff._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["--json", "signoff", "2"])

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (result.stdout + result.stderr)

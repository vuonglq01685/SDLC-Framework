"""Integration tests — mad-only unsign recovery (Story 4.12, AC4).

5-cell matrix + audit lens; POSIX-skip on signoff/journal write paths.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from _auto_mad_helpers import (
    _CLAR_ID,
    _bootstrap_journal,
    _write_approved_signoff,
)
from sdlc.cli.main import app
from sdlc.cli.unsign import _EMPTY_MSG, _EVENT_SENTINEL, _MAD_APPROVED_BY
from sdlc.engine.auto_mad import _build_resolution_body
from sdlc.engine.stop_clarification import OpenClarificationTrigger
from sdlc.journal import iter_entries
from sdlc.signoff import (
    ArtifactRef,
    SignoffRecord,
    SignoffState,
    compute_state,
    read_record,
    write_record,
)
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.state.model import State

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only signoff path in v1"),
]

_runner = CliRunner()


def _invoke_unsign(tmp_path: Path, *extra: str, json_out: bool = False) -> object:
    args = (["--json"] if json_out else []) + ["unsign", *extra]
    with unittest.mock.patch("sdlc.cli.unsign._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _write_mad_signoff(tmp_path: Path, phase: int, rel: str) -> None:
    artifact_path = tmp_path / rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if not artifact_path.is_file():
        artifact_path.write_text(f"# Phase {phase}\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=phase,
            artifacts=(ArtifactRef(path=rel, hash=artifact_hash),),
            approved_by=_MAD_APPROVED_BY,
            approved_at="2026-06-22T12:00:00.000Z",
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at="2026-06-22T12:00:00.000Z",
        ),
        repo_root=tmp_path,
    )
    phase_dir = {1: "01-Requirement", 2: "02-Architecture"}[phase]
    (tmp_path / phase_dir / "SIGNOFF.md").write_text(
        "approved: true\napproved_by: ai-mad-mode\n",
        encoding="utf-8",
    )


def _write_mad_resolution(tmp_path: Path, clar_id: str, open_body: str) -> Path:
    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / clar_id
    clar_dir.mkdir(parents=True, exist_ok=True)
    resolution_body = _build_resolution_body(
        clarification_id=clar_id,
        decision="Webhooks",
        resolved_at="2026-06-22T12:00:00.000Z",
        open_body=open_body,
        option_text="Webhooks",
    )
    (clar_dir / "resolution.md").write_text(resolution_body, encoding="utf-8")
    return clar_dir


def test_positive_unsign_mixed_human_and_mad(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    _write_approved_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    human_bytes = (tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml").read_bytes()
    _write_mad_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")

    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code == 0

    assert read_record(2, repo_root=tmp_path) is None
    assert compute_state(2, repo_root=tmp_path) == SignoffState.AWAITING_SIGNOFF
    assert (
        tmp_path / ".claude" / "state" / "signoffs" / "phase-1.yaml"
    ).read_bytes() == human_bytes

    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [e for e in iter_entries(journal) if e.kind == "signoff_unsigned"]
    assert len(entries) == 1
    assert entries[0].payload["phase"] == 2
    assert entries[0].payload["mad_only"] is True
    assert entries[0].payload["removed_count"] == 1
    assert entries[0].after_hash == _EVENT_SENTINEL


def test_empty_case_no_mutations(tmp_path: Path) -> None:
    journal, _, state = _bootstrap_journal(tmp_path)
    journal_mtime = journal.stat().st_mtime

    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code == 0
    assert _EMPTY_MSG in r.output
    assert list(iter_entries(journal)) == []
    assert journal.stat().st_mtime == journal_mtime
    assert state.read_text(encoding="utf-8") == "{}"


def test_preserve_invariant_multiple_human_and_mad(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    _write_approved_signoff(tmp_path, 1, "01-Requirement/01-PRODUCT.md")
    _write_mad_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")

    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code == 0
    assert read_record(1, repo_root=tmp_path) is not None
    assert read_record(2, repo_root=tmp_path) is None
    assert not (tmp_path / "02-Architecture" / "SIGNOFF.md").exists()


def test_include_clarifications_reverts_mad_resolution(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    open_body = f"# Open Clarification\n\nclarification_id: {_CLAR_ID}\n\nPick one.\n"
    clar_dir = _write_mad_resolution(tmp_path, _CLAR_ID, open_body)

    r = _invoke_unsign(tmp_path, "--mad-only", "--include-clarifications")
    assert r.exit_code == 0
    assert (clar_dir / "open_clarification.md").is_file()
    assert not (clar_dir / "resolution.md").exists()
    # Exact content (not .strip()) pins the `stripped + "\n"` newline contract of extract_open_body.
    assert (clar_dir / "open_clarification.md").read_text(
        encoding="utf-8"
    ) == open_body.strip() + "\n"

    trigger = OpenClarificationTrigger()
    assert trigger.check(repo_root=tmp_path, state=State()).fired is True

    journal = tmp_path / ".claude" / "state" / "journal.log"
    clar_entries = [
        e
        for e in iter_entries(journal)
        if e.kind == "signoff_unsigned" and "clarification_id" in e.payload
    ]
    assert len(clar_entries) == 1
    assert clar_entries[0].payload["clarification_id"] == _CLAR_ID


def test_idempotency_second_run_is_empty_case(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    _write_mad_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")

    first = _invoke_unsign(tmp_path, "--mad-only")
    assert first.exit_code == 0

    journal = tmp_path / ".claude" / "state" / "journal.log"
    # Run-1 must have actually done the work (not merely "run-2 added nothing"):
    assert read_record(2, repo_root=tmp_path) is None
    first_unsigned = [e for e in iter_entries(journal) if e.kind == "signoff_unsigned"]
    assert len(first_unsigned) == 1
    assert first_unsigned[0].payload["removed_count"] == 1
    count_after_first = len(list(iter_entries(journal)))

    second = _invoke_unsign(tmp_path, "--mad-only")
    assert second.exit_code == 0
    assert _EMPTY_MSG in second.output
    assert len(list(iter_entries(journal))) == count_after_first


def test_json_envelope_sorted_keys(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    _write_mad_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")

    r = _invoke_unsign(tmp_path, "--mad-only", json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert list(data.keys()) == sorted(data.keys())
    assert data["removed_count"] == 1


def test_mixed_signoff_and_clarification_removed_count_is_one_per_entry(tmp_path: Path) -> None:
    _bootstrap_journal(tmp_path)
    _write_mad_signoff(tmp_path, 2, "02-Architecture/ARCHITECTURE.md")
    open_body = f"# Open Clarification\n\nclarification_id: {_CLAR_ID}\n\nPick one.\n"
    _write_mad_resolution(tmp_path, _CLAR_ID, open_body)

    r = _invoke_unsign(tmp_path, "--mad-only", "--include-clarifications", json_out=True)
    assert r.exit_code == 0
    data = json.loads(r.output)
    # Run-level total stays in the envelope (1 signoff + 1 clarification)...
    assert data["removed_count"] == 2

    # ...while each per-event journal entry carries removed_count == 1 (CR4.12-D1, option c).
    journal = tmp_path / ".claude" / "state" / "journal.log"
    entries = [e for e in iter_entries(journal) if e.kind == "signoff_unsigned"]
    assert len(entries) == 2
    assert all(e.payload["removed_count"] == 1 for e in entries)

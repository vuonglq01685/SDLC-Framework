"""Unit tests for cli/unsign.py (Story 4.12, Task 1).

Covers mad-signoff selector, --json envelope, empty-case message, exit codes,
and --mad-only-required guard.
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
from sdlc.cli.unsign import (
    _EMPTY_MSG,
    _MAD_APPROVED_BY,
    extract_open_body_from_resolution,
    find_mad_resolution_dirs,
    select_mad_records,
)
from sdlc.signoff import ArtifactRef, SignoffRecord

pytestmark = pytest.mark.unit

_runner = CliRunner()


def _invoke_unsign(
    tmp_path: Path,
    *extra: str,
    json_out: bool = True,
) -> Any:
    args = (["--json"] if json_out else []) + ["unsign", *extra]
    with unittest.mock.patch("sdlc.cli.unsign._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _bootstrap_state(tmp_path: Path) -> None:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "journal.log").touch()
    (state_dir / "state.json").write_text("{}", encoding="utf-8")


def test_select_mad_records_filters_by_approved_by() -> None:
    human = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash="sha256:" + "a" * 64),),
        approved_by="lam@example.com",
        approved_at="2026-06-22T12:00:00.000Z",
        drafted_at="2026-06-10T09:00:00.000Z",
        validated_at="2026-06-22T12:00:00.000Z",
    )
    mad = SignoffRecord(
        phase=2,
        artifacts=(ArtifactRef(path="02-Architecture/ARCHITECTURE.md", hash="sha256:" + "b" * 64),),
        approved_by=_MAD_APPROVED_BY,
        approved_at="2026-06-22T12:00:00.000Z",
        drafted_at="2026-06-10T09:00:00.000Z",
        validated_at="2026-06-22T12:00:00.000Z",
    )
    selected = select_mad_records((human, mad))
    assert len(selected) == 1
    assert selected[0].phase == 2
    assert selected[0].approved_by == _MAD_APPROVED_BY


def test_extract_open_body_from_resolution_round_trip() -> None:
    open_body = "# Open Clarification\n\nclarification_id: clar-test01\n\nPick one.\n"
    resolution = (
        "# Mad-Mode Resolution\n\n"
        f"resolved_by: {_MAD_APPROVED_BY}\n"
        "clarification_id: clar-test01\n"
        "resolved_at: 2026-06-22T12:00:00.000Z\n"
        "decision: Webhooks\n\n"
        "## Original Open Clarification\n\n"
        f"{open_body}\n"
        "## Decision\n\n"
        "Webhooks\n"
    )
    # Exact equality (not .strip()) pins the `stripped + "\n"` newline contract.
    assert extract_open_body_from_resolution(resolution) == open_body


def test_find_mad_resolution_dirs_skips_human_resolved(tmp_path: Path) -> None:
    clar_root = tmp_path / "clarifications"
    human_dir = clar_root / "clar-human"
    human_dir.mkdir(parents=True)
    (human_dir / "resolution.md").write_text(
        "resolved_by: human@example.com\n\n## Original Open Clarification\n\nbody\n",
        encoding="utf-8",
    )
    mad_dir = clar_root / "clar-mad"
    mad_dir.mkdir(parents=True)
    (mad_dir / "resolution.md").write_text(
        f"resolved_by: {_MAD_APPROVED_BY}\n\n## Original Open Clarification\n\nbody\n",
        encoding="utf-8",
    )
    found = find_mad_resolution_dirs(clar_root)
    assert [p.name for p in found] == ["clar-mad"]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation needs privilege on Windows; exercised on the CI POSIX legs",
)
def test_find_mad_resolution_dirs_skips_symlinked_dir(tmp_path: Path) -> None:
    """ADR-037 (retro D1): a symlinked clarification dir (even if it holds a mad resolution)
    is never followed — it must not enter the revert loop."""
    clar_root = tmp_path / "repo" / ".claude" / "state" / "clarifications"
    clar_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "resolution.md").write_text(
        f"resolved_by: {_MAD_APPROVED_BY}\n\n## Original Open Clarification\n\nbody\n",
        encoding="utf-8",
    )
    (clar_root / "clar-evil").symlink_to(outside, target_is_directory=True)
    assert find_mad_resolution_dirs(clar_root) == ()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation needs privilege on Windows; exercised on the CI POSIX legs",
)
def test_revert_mad_clarification_rejects_symlinked_clar_dir(tmp_path: Path) -> None:
    """ADR-037 (retro D1) defense-in-depth: even if a symlinked clar dir reached the revert
    path, the write/unlink must be refused and the escaping target left untouched."""
    from sdlc.cli.unsign import _revert_mad_clarification
    from sdlc.errors import SecurityError

    repo_root = tmp_path / "repo"
    (repo_root / ".claude" / "state" / "clarifications").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    res = outside / "resolution.md"
    res.write_text(
        f"resolved_by: {_MAD_APPROVED_BY}\n\n## Original Open Clarification\n\nbody\n"
        "## Decision\n\nx\n",
        encoding="utf-8",
    )
    link = repo_root / ".claude" / "state" / "clarifications" / "clar-evil"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SecurityError):
        _revert_mad_clarification(clar_dir=link, repo_root=repo_root)
    # The escaping resolution survives and no open file leaked outside the repo.
    assert res.exists()
    assert not (outside / "open_clarification.md").exists()


def test_unsign_command_registered() -> None:
    result = _runner.invoke(app, ["unsign", "--help"])
    assert result.exit_code == 0
    assert "--mad-only" in result.output
    assert "--include-clarifications" in result.output


def test_bare_unsign_without_mad_only_errors(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    r = _invoke_unsign(tmp_path)
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_USER_INPUT"
    assert "--mad-only" in data["error"]["message"]


def test_not_initialized_exits_nonzero(tmp_path: Path) -> None:
    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code != 0
    data = json.loads(r.output)
    assert data["error"]["code"] == "ERR_NOT_INITIALIZED"


def test_empty_case_exit_zero_and_exact_message(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _bootstrap_state(tmp_path)
    r = _invoke_unsign(tmp_path, "--mad-only", json_out=False)
    assert r.exit_code == 0
    assert _EMPTY_MSG in r.output


def test_empty_case_json_removed_count_zero(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _bootstrap_state(tmp_path)
    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["command"] == "unsign"
    assert data["removed_count"] == 0
    assert data["outcome"] == "success"


def test_empty_case_appends_no_signoff_unsigned_entry(tmp_path: Path) -> None:
    from sdlc.journal import iter_entries

    _init_repo(tmp_path)
    journal = tmp_path / ".claude" / "state" / "journal.log"
    before = [e.kind for e in iter_entries(journal)]
    _invoke_unsign(tmp_path, "--mad-only")
    after = [e.kind for e in iter_entries(journal)]
    assert after == before
    assert "signoff_unsigned" not in after


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only signoff path in v1")
def test_json_envelope_reports_removed_count_after_unsign(tmp_path: Path) -> None:
    from sdlc.signoff import write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    _init_repo(tmp_path)
    _bootstrap_state(tmp_path)
    artifact = tmp_path / "02-Architecture" / "ARCHITECTURE.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("# Arch\n", encoding="utf-8")
    artifact_hash = compute_artifact_hash(artifact, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=2,
            artifacts=(ArtifactRef(path="02-Architecture/ARCHITECTURE.md", hash=artifact_hash),),
            approved_by=_MAD_APPROVED_BY,
            approved_at="2026-06-22T12:00:00.000Z",
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at="2026-06-22T12:00:00.000Z",
        ),
        repo_root=tmp_path,
    )
    draft = tmp_path / "02-Architecture" / "SIGNOFF.md"
    draft.write_text("approved: true\napproved_by: ai-mad-mode\n", encoding="utf-8")

    r = _invoke_unsign(tmp_path, "--mad-only")
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["removed_count"] == 1
    assert data["removed_phases"] == [2]

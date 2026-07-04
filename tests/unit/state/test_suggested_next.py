"""Unit tests for sdlc.state.suggested_next (Story 5.18 D2 — single-source lift).

`compute_suggested_next` is lifted verbatim from the Story 1.17
`cli/status.py::_compute_suggested_next` stub into a boundary-legal shared
module (`state/`) so BOTH `cli/status.py` and `dashboard/routes/resume.py`
delegate to the SAME function — "same command" holds by construction, not by
parallel re-derivation.
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.dashboard.routes.resume import build_resume_token
from sdlc.state import state_to_canonical_bytes
from sdlc.state.model import State
from sdlc.state.suggested_next import compute_suggested_next


def test_fresh_project_suggests_sdlc_start() -> None:
    state = State(phase=1, epics={})
    assert compute_suggested_next(state) == '/sdlc-start "<idea>"'


def test_phase_1_with_epics_suggests_scan() -> None:
    state = State(phase=1, epics={"epic-1": {}})
    assert compute_suggested_next(state) == "sdlc scan"


def test_later_phase_suggests_scan() -> None:
    state = State(phase=2, epics={})
    assert compute_suggested_next(state) == "sdlc scan"


def test_cli_status_and_dashboard_resume_route_agree_by_construction(
    tmp_path: Path,
) -> None:
    """Task 3 parity test (D2): `sdlc status` and `GET /api/resume` must emit the
    IDENTICAL suggested-next command for the same state -- because both delegate
    to this one function, not because two independent implementations happen to
    agree. Drives `run_status`'s JSON envelope and `build_resume_token` from the
    SAME on-disk state.json and compares their `suggested_next`/
    `suggested_next_command` fields.
    """
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    state = State(phase=1, epics={"epic-1": {}})
    (state_dir / "state.json").write_bytes(state_to_canonical_bytes(state))
    (state_dir / "journal.log").touch()

    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=tmp_path):
        result = CliRunner().invoke(app, ["--json", "status"])
    assert result.exit_code == 0, result.output
    cli_suggested = json.loads(result.stdout)["suggested_next"]

    route_token = build_resume_token(tmp_path)
    assert route_token is not None
    assert route_token["suggested_next_command"] == cli_suggested


def test_cli_status_and_dashboard_resume_route_agree_on_fresh_project(
    tmp_path: Path,
) -> None:
    """P7 (review): the parity test above only covers the ``sdlc scan`` branch.
    Prove the OTHER branch too -- a fresh phase-1/no-epics project must have
    ``sdlc status`` and ``GET /api/resume`` agree on ``/sdlc-start "<idea>"`` --
    so the single-source guarantee is exercised across BOTH
    ``compute_suggested_next`` outcomes, not just one.
    """
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    state = State(phase=1, epics={})
    (state_dir / "state.json").write_bytes(state_to_canonical_bytes(state))
    (state_dir / "journal.log").touch()

    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=tmp_path):
        result = CliRunner().invoke(app, ["--json", "status"])
    assert result.exit_code == 0, result.output
    cli_suggested = json.loads(result.stdout)["suggested_next"]
    assert cli_suggested == '/sdlc-start "<idea>"'

    route_token = build_resume_token(tmp_path)
    assert route_token is not None
    assert route_token["suggested_next_command"] == cli_suggested

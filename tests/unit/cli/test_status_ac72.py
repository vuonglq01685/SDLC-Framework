"""AC7.2 journal-timestamp and zero-args behavior tests for sdlc.cli.status.

Split from test_status.py to satisfy the 400-LOC cap (Architecture §765 + NFR-MAINT-3).
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.state import State, state_to_canonical_bytes

pytestmark = pytest.mark.unit

runner = CliRunner()


def _bootstrap_project(root: Path) -> None:
    state_dir = root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_bytes(state_to_canonical_bytes(State()))
    (state_dir / "journal.log").touch()


@pytest.fixture()
def bootstrapped(tmp_path: Path) -> Path:
    _bootstrap_project(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# AC7.2 — `test_status_last_updated_uses_latest_journal_ts`
# ---------------------------------------------------------------------------


def test_status_last_updated_uses_latest_journal_ts(bootstrapped: Path) -> None:
    """status renders the timestamp of the latest journal entry (AC7.2)."""
    journal_path = bootstrapped / ".claude" / "state" / "journal.log"
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync

    expected_ts = "2026-05-09T12:34:56.789Z"
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts=expected_ts,
        actor="cli",
        kind="scan_completed",
        target_id="state",
        before_hash=None,
        after_hash="sha256:" + "c" * 64,
        payload={"epic_count": 0, "story_count": 0, "task_count": 0},
    )
    append_sync(entry, journal_path=journal_path)

    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        result = runner.invoke(app, ["--json", "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    # JSON mode emits the literal RFC 3339 ts.
    assert payload["last_updated_ts"] == expected_ts


# ---------------------------------------------------------------------------
# AC7.2 — `test_status_zero_args_invokes_help_or_status_per_typer_default`
# ---------------------------------------------------------------------------


def test_status_zero_args_invokes_help_or_status_per_typer_default(bootstrapped: Path) -> None:
    """`sdlc status` (no extra args) runs the status command, NOT Typer's auto-help.

    Typer's `no_args_is_help=True` triggers help when no command is given to the root
    app (`sdlc` alone). When a subcommand is named (`sdlc status`), that subcommand
    runs even without further args. This test pins that behavior so a future Typer
    setting change cannot silently swap status for help (AC7.2).
    """
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    # Help output starts with `Usage:`; status output contains the resume card header.
    assert "Usage:" not in result.stdout
    assert "Phase:" in result.stdout

"""Unit tests for sdlc.cli.status (Story 1.17, AC7.2)."""

from __future__ import annotations

import json
import logging
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.cli.status import run_status
from sdlc.state import State, state_to_canonical_bytes

pytestmark = pytest.mark.unit

runner = CliRunner()


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def _bootstrap_project(root: Path) -> None:
    state_dir = root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_bytes(state_to_canonical_bytes(State()))
    (state_dir / "journal.log").touch()


@pytest.fixture()
def bootstrapped(tmp_path: Path) -> Path:
    _bootstrap_project(tmp_path)
    return tmp_path


def test_status_refuses_when_state_not_initialized(tmp_path: Path) -> None:
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=tmp_path),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_status(ctx=ctx)
    assert exc_info.value.exit_code == 1


def test_status_fresh_project_suggests_sdlc_start(
    bootstrapped: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _make_ctx()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        run_status(ctx=ctx)
    captured = capsys.readouterr()
    assert 'Suggested next: /sdlc-start "<idea>"' in captured.out


def test_status_phase_line_renders_phase_1_requirement(
    bootstrapped: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _make_ctx()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        run_status(ctx=ctx)
    captured = capsys.readouterr()
    assert "Phase: 1 (Requirement)" in captured.out


def test_status_last_updated_never_when_journal_empty(
    bootstrapped: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _make_ctx()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        run_status(ctx=ctx)
    captured = capsys.readouterr()
    assert "never" in captured.out.lower() or "sdlc scan" in captured.out


def test_status_json_mode_emits_canonical_envelope(bootstrapped: Path) -> None:
    expected_keys = {
        "command",
        "project_name",
        "project_root",
        "phase",
        "phase_name",
        "last_updated_ts",
        "epic_count",
        "story_count",
        "task_count",
        "suggested_next",
        "next_monotonic_seq",
    }
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        result = runner.invoke(app, ["--json", "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == expected_keys
    assert payload["command"] == "status"
    assert payload["phase"] == 1
    assert payload["phase_name"] == "Requirement"
    assert payload["last_updated_ts"] is None


def test_status_does_not_write_state_or_journal(bootstrapped: Path) -> None:
    state_path = bootstrapped / ".claude" / "state" / "state.json"
    journal_path = bootstrapped / ".claude" / "state" / "journal.log"
    state_mtime_before = state_path.stat().st_mtime
    journal_mtime_before = journal_path.stat().st_mtime

    ctx = _make_ctx()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        run_status(ctx=ctx)

    assert state_path.stat().st_mtime == state_mtime_before
    assert journal_path.stat().st_mtime == journal_mtime_before


def test_status_unknown_phase_logs_warning(
    bootstrapped: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_path = bootstrapped / ".claude" / "state" / "state.json"
    payload = {
        "schema_version": 1,
        "next_monotonic_seq": 0,
        "phase": 99,
        "epics": {},
        "stories": {},
        "tasks": {},
    }
    state_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped),
        caplog.at_level(logging.WARNING, logger="sdlc.cli.status"),
    ):
        run_status(ctx=ctx)
    captured = capsys.readouterr()
    assert "Phase: 99 (unknown)" in captured.out
    assert any("phase" in r.message.lower() or "99" in r.message for r in caplog.records)


def test_status_json_null_when_journal_empty(bootstrapped: Path) -> None:
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        result = runner.invoke(app, ["--json", "status"])
    payload = json.loads(result.stdout)
    assert payload["last_updated_ts"] is None


def test_status_resolves_project_name_from_pyproject(
    bootstrapped: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (bootstrapped / "pyproject.toml").write_text(
        '[project]\nname = "my-test-project"\n', encoding="utf-8"
    )
    ctx = _make_ctx()
    with unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped):
        run_status(ctx=ctx)
    captured = capsys.readouterr()
    assert "my-test-project" in captured.out


# ---------------------------------------------------------------------------
# _get_repo_root_or_cwd (lines 39-55)
# ---------------------------------------------------------------------------


def test_status_get_repo_root_uses_git_top_level(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Successful git rev-parse output is taken as the repo root."""
    from sdlc.cli.status import _get_repo_root_or_cwd

    fake_root = tmp_path / "fake-repo"
    fake_root.mkdir()

    class _Result:
        returncode = 0
        stdout = f"{fake_root}\n"

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", lambda *a, **k: _Result())
    assert _get_repo_root_or_cwd() == fake_root.resolve()


def test_status_get_repo_root_falls_back_on_subprocess_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SubprocessError from git falls back to cwd."""
    import subprocess as _sp

    from sdlc.cli.status import _get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    def _raise(*a: object, **k: object) -> object:
        raise _sp.SubprocessError("simulated")

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", _raise)
    assert _get_repo_root_or_cwd() == tmp_path.resolve()


def test_status_get_repo_root_falls_back_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty stdout from git falls back to cwd."""
    from sdlc.cli.status import _get_repo_root_or_cwd

    monkeypatch.chdir(tmp_path)

    class _Result:
        returncode = 0
        stdout = "\n"

    monkeypatch.setattr("sdlc.cli._paths.subprocess.run", lambda *a, **k: _Result())
    assert _get_repo_root_or_cwd() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# _resolve_project_name branches (lines 64-65, 67→69)
# ---------------------------------------------------------------------------


def test_resolve_project_name_returns_dir_name_on_oserror(tmp_path: Path) -> None:
    """OSError reading pyproject.toml falls back to root.name."""
    from sdlc.cli.status import _resolve_project_name

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")
    # Patch both the 3.11+ tomllib path (`Path.open`) and the 3.10 fallback
    # (`Path.read_text`) so the test asserts the OSError fallback regardless of
    # the runtime branch we're on.
    with (
        unittest.mock.patch.object(
            type(pyproject), "open", side_effect=OSError("permission denied")
        ),
        unittest.mock.patch.object(
            type(pyproject), "read_text", side_effect=OSError("permission denied")
        ),
    ):
        result = _resolve_project_name(tmp_path)
    assert result == tmp_path.name


def test_resolve_project_name_returns_dir_name_when_no_match(tmp_path: Path) -> None:
    """pyproject.toml exists but has no `name = ...` line → falls back to dir name."""
    from sdlc.cli.status import _resolve_project_name

    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    result = _resolve_project_name(tmp_path)
    assert result == tmp_path.name


# Note: _resolve_project_name helper unit tests live in test_status_resolve.py
# (split off in Story 1.17 review to keep this file under the 400-LOC cap).


# ---------------------------------------------------------------------------
# _get_last_journal_ts branches (lines 77, 80)
# ---------------------------------------------------------------------------


def test_get_last_journal_ts_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Missing journal.log → returns None without error."""
    from sdlc.cli.status import _get_last_journal_ts

    result = _get_last_journal_ts(tmp_path / "nonexistent.log")
    assert result is None


def test_get_last_journal_ts_returns_ts_from_entries(tmp_path: Path) -> None:
    """Journal with entries → returns ts of last entry."""
    from sdlc.cli.status import _get_last_journal_ts
    from sdlc.contracts.journal_entry import JournalEntry

    journal_path = tmp_path / "journal.log"
    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=0,
        ts="2024-06-15T12:00:00.000Z",
        actor="cli",
        kind="scan_completed",
        target_id="state",
        before_hash=None,
        after_hash="sha256:" + "b" * 64,
        payload={},
    )
    journal_path.write_text(entry.model_dump_json() + "\n", encoding="utf-8")
    result = _get_last_journal_ts(journal_path)
    assert result == "2024-06-15T12:00:00.000Z"


# ---------------------------------------------------------------------------
# _format_ts_local invalid input (lines 86-92)
# ---------------------------------------------------------------------------


def test_format_ts_local_returns_raw_string_on_invalid_input() -> None:
    """Invalid ISO timestamp string is returned verbatim (ValueError branch)."""
    from sdlc.cli.status import _format_ts_local

    bad_ts = "not-a-timestamp"
    result = _format_ts_local(bad_ts)
    assert result == bad_ts


# ---------------------------------------------------------------------------
# _read_state_portable removed in Story 1.17 review — see tests/unit/state/test_state_read.py
# for the canonical schema-mismatch / invalid-JSON coverage on `sdlc.state.read_state`.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# run_status state-read failure → ERR_INFRASTRUCTURE (exit 3) (Story 1.17 review)
# ---------------------------------------------------------------------------


def test_status_emits_error_when_state_read_raises(bootstrapped: Path) -> None:
    """A StateError from sdlc.state.read_state surfaces as ERR_INFRASTRUCTURE (exit 3)."""
    from sdlc.errors import StateError

    ctx = _make_ctx()
    with (
        unittest.mock.patch("sdlc.cli.status._get_repo_root_or_cwd", return_value=bootstrapped),
        unittest.mock.patch("sdlc.state.read_state", side_effect=StateError("disk error")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        run_status(ctx=ctx)
    assert exc_info.value.exit_code == 3


# ---------------------------------------------------------------------------
# AC7.2 — `test_status_last_updated_uses_latest_journal_ts` (added in Story 1.17 review)
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

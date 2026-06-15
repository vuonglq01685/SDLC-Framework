from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only — atomic state write"),
]

runner = CliRunner()


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def _bootstrap_state_dir(root: Path) -> None:
    """Create .claude/state/ directory (but NOT state.json or journal.log)."""
    (root / ".claude" / "state").mkdir(parents=True, exist_ok=True)


def _write_valid_state(root: Path) -> None:
    from sdlc.state import State, write_state_atomic_sync

    state_path = root / ".claude" / "state" / "state.json"
    write_state_atomic_sync(State(), state_path)


def _write_journal_entries(root: Path, n: int) -> None:
    import datetime

    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.journal import append_sync

    journal_path = root / ".claude" / "state" / "journal.log"

    def _ts() -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    for i in range(n):
        entry = JournalEntry(
            schema_version=1,
            monotonic_seq=i,
            ts=_ts(),
            actor="test",
            kind="state_mutation",
            target_id="state",
            before_hash=None,
            after_hash=f"sha256:{'a' * 64}",
            payload={"seq": i},
        )
        append_sync(entry, journal_path=journal_path)


def _patch_root(root: Path) -> unittest.mock._patch:  # type: ignore[type-arg]
    return unittest.mock.patch("sdlc.cli.rebuild_state._get_repo_root_or_cwd", return_value=root)


# ---------------------------------------------------------------------------
# Refusal tests
# ---------------------------------------------------------------------------


def test_rebuild_state_refuses_when_state_dir_missing(tmp_path: Path) -> None:
    ctx = _make_ctx()
    with _patch_root(tmp_path), pytest.raises(typer.Exit) as exc_info:
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)
    assert exc_info.value.exit_code == 1


def test_rebuild_state_refuses_when_state_dir_missing_stderr_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _make_ctx()
    with _patch_root(tmp_path), pytest.raises(typer.Exit):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)
    captured = capsys.readouterr()
    assert "not initialized" in captured.err.lower() or "sdlc init" in captured.err


def test_rebuild_state_refuses_when_journal_and_state_both_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _bootstrap_state_dir(tmp_path)
    ctx = _make_ctx()
    with _patch_root(tmp_path), pytest.raises(typer.Exit) as exc_info:
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)
    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    assert "no journal at" in captured.err
    assert "recovery requires either journal or backup" in captured.err
    assert "Check for backups at:" in captured.err


def test_rebuild_state_refuses_when_only_journal_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _bootstrap_state_dir(tmp_path)
    _write_valid_state(tmp_path)
    # No journal.log
    ctx = _make_ctx()
    with _patch_root(tmp_path), pytest.raises(typer.Exit) as exc_info:
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)
    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    assert "no journal at" in captured.err


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


def test_rebuild_state_succeeds_with_intact_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _bootstrap_state_dir(tmp_path)
    _write_valid_state(tmp_path)
    _write_journal_entries(tmp_path, 3)
    # Delete state.json to simulate disaster
    (tmp_path / ".claude" / "state" / "state.json").unlink()

    ctx = _make_ctx()
    with _patch_root(tmp_path):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)

    captured = capsys.readouterr()
    assert "state rebuilt from 3 journal entries" in captured.out
    assert (tmp_path / ".claude" / "state" / "state.json").exists()


def test_rebuild_state_succeeds_with_empty_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _bootstrap_state_dir(tmp_path)
    # Create an empty journal (just touch)
    (tmp_path / ".claude" / "state" / "journal.log").touch()

    ctx = _make_ctx()
    with _patch_root(tmp_path):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)

    captured = capsys.readouterr()
    assert "state rebuilt from 0 journal entries" in captured.out
    state_path = tmp_path / ".claude" / "state" / "state.json"
    assert state_path.exists()
    data = json.loads(state_path.read_bytes())
    assert data == {
        "auto_loop_status": "idle",  # Story 4.1: additive State field (default idle)
        "epics": {},
        "next_monotonic_seq": 0,
        "phase": 1,
        "schema_version": 1,
        "stop_reason": None,  # Story 4.1: additive State field (default None)
        "stories": {},
        "tasks": {},
    }


def test_rebuild_state_succeeds_with_state_already_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _bootstrap_state_dir(tmp_path)
    _write_valid_state(tmp_path)
    _write_journal_entries(tmp_path, 2)
    # Do NOT delete state.json — rebuild overwrites it

    ctx = _make_ctx()
    with _patch_root(tmp_path):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)

    captured = capsys.readouterr()
    assert "state rebuilt from 2 journal entries" in captured.out

    # AC7.4: state.json is OVERWRITTEN with the rebuilt content (byte-equal to a direct
    # project_from_journal output). Use the same canonical-write pipeline for the oracle.
    from sdlc.state import (
        project_from_journal,
        write_state_atomic_sync,
    )

    rebuilt_state_path = tmp_path / ".claude" / "state" / "state.json"
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    oracle_path = tmp_path / "oracle_state.json"
    write_state_atomic_sync(project_from_journal(journal_path.resolve()), oracle_path.resolve())
    assert rebuilt_state_path.read_bytes() == oracle_path.read_bytes()


# ---------------------------------------------------------------------------
# Error dispatch tests
# ---------------------------------------------------------------------------


def test_rebuild_state_emits_journal_corrupt_on_seq_regression(tmp_path: Path) -> None:
    """In JSON mode the error code appears in the stderr envelope."""
    from sdlc.cli.main import app
    from sdlc.errors import JournalError

    _bootstrap_state_dir(tmp_path)
    (tmp_path / ".claude" / "state" / "journal.log").touch()

    corrupt_err = JournalError(
        "monotonic_seq regression at line 2 (prev_seq=1, next_seq=0)",
        # journal/reader.py emits "lineno" (not "line") in details — the dispatcher reads it.
        details={"step": "reader_invariant", "lineno": 2, "prev_seq": 1, "next_seq": 0},
    )
    with (
        _patch_root(tmp_path),
        unittest.mock.patch(
            "sdlc.state.rebuild.rebuild_state_from_journal", side_effect=corrupt_err
        ),
    ):
        result = runner.invoke(app, ["--json", "rebuild-state"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "ERR_JOURNAL_CORRUPT"
    # The user-facing message MUST surface the actual line number from details["lineno"].
    assert "monotonic_seq regression at line 2" in payload["error"]["message"]
    assert "(prev_seq=1, next_seq=0)" in payload["error"]["message"]


def test_rebuild_state_emits_schema_drift_on_unknown_version(tmp_path: Path) -> None:
    """In JSON mode the error code appears in the stderr envelope."""
    from sdlc.cli.main import app
    from sdlc.errors import JournalError

    _bootstrap_state_dir(tmp_path)
    (tmp_path / ".claude" / "state" / "journal.log").touch()

    schema_drift_err = JournalError(
        "unknown schema_version=2 for kind=state_mutation; run sdlc migrate-v2",
        details={"step": "project_unknown_schema", "schema_version": 2},
    )
    with (
        _patch_root(tmp_path),
        unittest.mock.patch(
            "sdlc.state.rebuild.rebuild_state_from_journal", side_effect=schema_drift_err
        ),
    ):
        result = runner.invoke(app, ["--json", "rebuild-state"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "ERR_JOURNAL_SCHEMA_DRIFT"


# ---------------------------------------------------------------------------
# JSON mode tests
# ---------------------------------------------------------------------------


def test_rebuild_state_json_mode_success_envelope(tmp_path: Path) -> None:
    from sdlc.cli.main import app

    _bootstrap_state_dir(tmp_path)
    _write_journal_entries(tmp_path, 2)

    with _patch_root(tmp_path):
        result = runner.invoke(app, ["--json", "rebuild-state"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert set(payload.keys()) >= {
        "command",
        "result",
        "entries_replayed",
        "state_path",
        "journal_path",
    }
    assert payload["result"] == "success"
    assert isinstance(payload["entries_replayed"], int)


def test_rebuild_state_json_mode_no_recovery_source_envelope(tmp_path: Path) -> None:
    from sdlc.cli.main import app

    _bootstrap_state_dir(tmp_path)
    # Leave both state.json and journal.log absent

    with _patch_root(tmp_path):
        result = runner.invoke(app, ["--json", "rebuild-state"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "ERR_NO_RECOVERY_SOURCE"
    details = payload["error"]["details"]
    assert "journal_path" in details
    assert "state_path" in details
    assert "backup_dir" in details


# ---------------------------------------------------------------------------
# Idempotency + journal-untouched tests
# ---------------------------------------------------------------------------


def test_rebuild_state_idempotent(tmp_path: Path) -> None:
    _bootstrap_state_dir(tmp_path)
    _write_journal_entries(tmp_path, 3)

    state_path = tmp_path / ".claude" / "state" / "state.json"

    ctx = _make_ctx()
    with _patch_root(tmp_path):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)
    bytes_first = state_path.read_bytes()

    ctx2 = _make_ctx()
    with _patch_root(tmp_path):
        run_rebuild_state(ctx=ctx2)
    bytes_second = state_path.read_bytes()

    assert bytes_first == bytes_second


def test_rebuild_state_does_not_mutate_journal(tmp_path: Path) -> None:
    _bootstrap_state_dir(tmp_path)
    _write_journal_entries(tmp_path, 3)

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_bytes_before = journal_path.read_bytes()

    ctx = _make_ctx()
    with _patch_root(tmp_path):
        from sdlc.cli.rebuild_state import run_rebuild_state

        run_rebuild_state(ctx=ctx)

    assert journal_path.read_bytes() == journal_bytes_before

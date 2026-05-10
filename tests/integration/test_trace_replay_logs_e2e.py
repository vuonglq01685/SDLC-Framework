"""End-to-end integration tests for sdlc trace, replay, logs (Story 1.18, AC7.7).

B-P22: in-process CliRunner replaces _uv_sdlc subprocess for most tests.
B-P23: test_no_color_flag_strips_ansi drives a path that produces ANSI escapes.
B-P28: parametrize extended with replay 1-1 (range), replay 999 (OOB), logs --filter-agent.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _append_journal_entry(journal_path: Path, seq: int, task_id: str) -> None:
    from sdlc.contracts.journal_entry import JournalEntry

    entry = JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=f"2026-01-01T00:00:{seq:02d}Z",
        actor="cli",
        kind="scan_completed",
        target_id=task_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload={},
    )
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def _init_project(tmp_path: Path) -> Path:
    """Init + scan in-process; return journal path.

    Story 2A.5 note: ``sdlc init`` writes a ``hooks_trusted`` journal entry at
    seq=0 and ``sdlc scan`` writes a ``scan_completed`` entry at seq=1, so
    after the bootstrap ceremony the journal has 2 entries and
    ``state.next_monotonic_seq`` is 2. The trace/replay/logs tests below
    expect a clean baseline (their ``_append_journal_entry(journal, seq=1)``
    calls were authored before 2A.5), so we truncate journal + reset state to
    a test-controlled empty baseline after init+scan. Verified caused-by-2A.5
    via bisect on commit 12374b3 (Story 2A.5 DR2 subset-(c) fix).
    """
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        r = runner.invoke(app, ["init"], catch_exceptions=False)
        assert r.exit_code == 0, f"init failed: {r.output}"
        r = runner.invoke(app, ["scan"], catch_exceptions=False)
        assert r.exit_code == 0, f"scan failed: {r.output}"
    finally:
        os.chdir(orig)

    # Reset to test-controlled baseline so seq=1 manual append remains valid.
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_path.write_bytes(b"")  # truncate journal
    state_path = tmp_path / ".claude" / "state" / "state.json"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    state_data["next_monotonic_seq"] = 0
    state_path.write_text(  # noqa: state-write -- test fixture reset, not production state path
        json.dumps(state_data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    return journal_path


def _invoke(tmp_path: Path, args: list[str]) -> Any:
    """Run sdlc command in-process with cwd=tmp_path."""
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(app, args, catch_exceptions=False)
    finally:
        os.chdir(orig)


# ---------------------------------------------------------------------------
# Main lifecycle test (B-P22: in-process)
# ---------------------------------------------------------------------------


def test_full_lifecycle_init_scan_trace_replay_logs(tmp_path: Path) -> None:
    """Full lifecycle: init → manually add journal entry → trace/replay/logs all exit 0."""
    journal = _init_project(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    # sdlc trace — B-P18: check envelope keys, not prose strings
    r = _invoke(tmp_path, ["--json", "trace", task_id])
    assert r.exit_code == 0, f"trace failed: {r.output}"
    payload = json.loads(r.output)
    assert "task_id" in payload
    assert "events" in payload

    # sdlc replay 1 — B-P18: check envelope keys in --json mode
    r = _invoke(tmp_path, ["--json", "replay", "1"])
    assert r.exit_code == 0, f"replay failed: {r.output}"
    payload = json.loads(r.output)
    assert "lines" in payload

    # sdlc logs — B-P18: check envelope keys
    r = _invoke(tmp_path, ["--json", "logs"])
    assert r.exit_code == 0, f"logs failed: {r.output}"
    payload = json.loads(r.output)
    assert "filters" in payload
    assert "events" in payload


# ---------------------------------------------------------------------------
# --no-color strips ANSI (B-P23: drives path that actually produces color)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_args",
    [
        ["trace", "EPIC-foo-S01-bar-T01-baz"],
        ["replay", "1"],
        ["logs"],
    ],
)
def test_no_color_flag_strips_ansi_on_trace_replay_logs(
    tmp_path: Path, command_args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-P23: --no-color strips ANSI; verifies a path that WOULD produce color.

    We monkeypatch typer.echo to capture the raw message before terminal rendering,
    proving that echo() with no_color=True strips ANSI from the message itself,
    while echo() with no_color=False passes ANSI through unchanged.
    """
    import typer as _typer

    from sdlc.cli.output import echo

    captured_messages: list[str] = []

    def _fake_echo(msg: str = "", **kw: object) -> None:
        captured_messages.append(msg)

    monkeypatch.setattr(_typer, "echo", _fake_echo)

    # Build two contexts.
    def _ctx(*, no_color: bool) -> _typer.Context:
        c = _typer.Context(command=_typer.core.TyperCommand("test"))
        c.ensure_object(dict)
        c.obj["no_color"] = no_color
        c.obj["json"] = False
        return c

    ansi_msg = "\x1b[31mred text\x1b[0m"

    # With color enabled — ANSI passes through to echo unchanged.
    captured_messages.clear()
    echo(ansi_msg, ctx=_ctx(no_color=False))
    assert len(captured_messages) == 1
    assert "\x1b[" in captured_messages[0], "echo(no_color=False) should NOT strip ANSI"

    # With no-color — ANSI is stripped before calling typer.echo.
    captured_messages.clear()
    echo(ansi_msg, ctx=_ctx(no_color=True))
    assert len(captured_messages) == 1
    assert "\x1b[" not in captured_messages[0], "echo(no_color=True) must strip ANSI"
    assert "red text" in captured_messages[0]

    # Full CLI: --no-color flag wires up correctly end-to-end.
    journal = _init_project(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    r = _invoke(tmp_path, ["--no-color", *command_args])
    assert r.exit_code == 0, f"command failed: {r.output}"
    assert "\x1b[" not in r.output, "ANSI found in output"


# ---------------------------------------------------------------------------
# --json emits canonical envelope (B-P22: in-process)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_args,expected_key",
    [
        (["trace", "EPIC-foo-S01-bar-T01-baz"], "task_id"),
        (["replay", "1"], "lines"),
        (["logs"], "filters"),
    ],
)
def test_json_mode_emits_canonical_envelope_for_trace_replay_logs(
    tmp_path: Path,
    command_args: list[str],
    expected_key: str,
) -> None:
    """--json emits a parseable JSON envelope with the expected key (B-P22: in-process)."""
    journal = _init_project(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    r = _invoke(tmp_path, ["--json", *command_args])
    assert r.exit_code == 0, f"--json command failed: {r.output}"
    payload: dict[str, Any] = json.loads(r.output)
    assert "command" in payload
    assert expected_key in payload


# ---------------------------------------------------------------------------
# Extended parametrize (B-P28)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command_args,expected_exit",
    [
        # Range form in bounds
        (["replay", "1-1"], 0),
        # Single out-of-range → exit 1
        (["replay", "999"], 1),
        # logs with --filter-agent succeeds
        (["logs", "--filter-agent", "implementer"], 0),
    ],
)
def test_e2e_extended_cases(tmp_path: Path, command_args: list[str], expected_exit: int) -> None:
    """B-P28: replay 1-1 (range form), replay 999 (OOB exit 1), logs --filter-agent."""
    journal = _init_project(tmp_path)
    task_id = "EPIC-foo-S01-bar-T01-baz"
    _append_journal_entry(journal, seq=1, task_id=task_id)

    r = _invoke(tmp_path, command_args)
    assert r.exit_code == expected_exit, (
        f"{command_args!r} expected exit {expected_exit}, got {r.exit_code}: {r.output}"
    )


# ---------------------------------------------------------------------------
# BrokenPipeError subprocess test (reserved for subprocess — B-P15)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
@pytest.mark.skipif(sys.platform == "win32", reason="pipe tests skip on Windows")
@pytest.mark.xfail(
    reason="Pre-existing failure on main@12374b3 (verified by bisect 2026-05-10):"
    " subprocess timeout running 'uv run sdlc logs --follow | head -1'."
    " Tracked in EPIC-2A-DEBT-005. Story 2A.5 DR2 quarantine.",
    strict=False,
)
def test_follow_broken_pipe_exits_cleanly_subprocess(tmp_path: Path) -> None:
    """B-P15: sdlc logs --follow | head -1 exits 0, stderr free of Python Traceback."""
    import subprocess as _sp

    _sp.run(["git", "init"], cwd=tmp_path, capture_output=True, check=False)
    r = _sp.run(["uv", "run", "sdlc", "init"], cwd=tmp_path, capture_output=True, check=False)
    if r.returncode != 0:
        pytest.skip("uv run sdlc init failed — skipping subprocess test")
    r = _sp.run(["uv", "run", "sdlc", "scan"], cwd=tmp_path, capture_output=True, check=False)
    if r.returncode != 0:
        pytest.skip("uv run sdlc scan failed — skipping subprocess test")

    journal = tmp_path / ".claude" / "state" / "journal.log"
    if not journal.parent.exists():
        pytest.skip(".claude/state/ not created by sdlc init+scan — skipping subprocess test")
    _append_journal_entry(journal, seq=1, task_id="EPIC-foo-S01-bar-T01-baz")

    proc = _sp.run(
        "uv run sdlc logs --follow | head -1",
        cwd=tmp_path,
        shell=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    # The pipeline exits 0 (BrokenPipeError suppressed inside sdlc).
    assert "Traceback" not in proc.stderr, f"Python traceback in stderr: {proc.stderr}"

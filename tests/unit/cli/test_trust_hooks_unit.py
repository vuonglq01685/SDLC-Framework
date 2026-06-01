"""Unit tests for sdlc.cli.trust_hooks (Story 2B.10 coverage patch).

The integration tests in tests/integration/test_trust_hooks_cmd.py exercise
trust-hooks via subprocess, which gives zero import-level coverage. These unit
tests call the module directly with a tmp_path workspace to cover the key paths
in _journal_and_advance_seq and run_trust_hooks.

POSIX-only: append_sync and write_state_atomic_sync use fcntl + O_APPEND.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: fcntl + O_APPEND"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create minimal initialised workspace; return (root, state_path, journal_path)."""
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    journal_path = state_dir / "journal.log"

    # Write a valid State JSON (matching sdlc.state.model.State default fields).
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "next_monotonic_seq": 0,
                "phase": 1,
                "epics": {},
                "stories": {},
                "tasks": {},
            }
        ),
        encoding="utf-8",
    )
    journal_path.touch()
    return tmp_path, state_path, journal_path


def _make_ctx() -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = False
    ctx.obj["json"] = False
    return ctx


# ---------------------------------------------------------------------------
# _journal_and_advance_seq — happy path
# ---------------------------------------------------------------------------


def test_journal_and_advance_seq_appends_hooks_trusted_entry(tmp_path: Path) -> None:
    """_journal_and_advance_seq writes a hooks_trusted JournalEntry."""
    from sdlc.cli.trust_hooks import _journal_and_advance_seq

    _, state_path, journal_path = _make_workspace(tmp_path)
    ctx = _make_ctx()
    _ZERO = "sha256:" + "0" * 64
    _ONE = "sha256:" + "1" * 64

    _journal_and_advance_seq(
        hashes={"hook_a.py": _ZERO},
        before_hash=_ZERO,
        after_hash=_ONE,
        now="2026-06-01T00:00:00.000Z",
        state_path=state_path,
        journal_path=journal_path,
        ctx=ctx,
    )

    lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "hooks_trusted"
    assert entry["target_id"] == "hook-hashes"
    assert entry["monotonic_seq"] == 0
    assert entry["after_hash"] == _ONE
    assert "hook_a.py" in entry["payload"]["files"]


def test_journal_and_advance_seq_advances_monotonic_seq(tmp_path: Path) -> None:
    """_journal_and_advance_seq increments next_monotonic_seq in state.json."""
    from sdlc.cli.trust_hooks import _journal_and_advance_seq

    _, state_path, journal_path = _make_workspace(tmp_path)
    ctx = _make_ctx()
    _ZERO = "sha256:" + "0" * 64
    _ONE = "sha256:" + "1" * 64

    _journal_and_advance_seq(
        hashes={},
        before_hash=_ZERO,
        after_hash=_ONE,
        now="2026-06-01T00:00:00.000Z",
        state_path=state_path,
        journal_path=journal_path,
        ctx=ctx,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["next_monotonic_seq"] == 1


def test_journal_and_advance_seq_multiple_calls_increment_seq(tmp_path: Path) -> None:
    """Sequential calls each increment next_monotonic_seq by 1."""
    from sdlc.cli.trust_hooks import _journal_and_advance_seq

    _, state_path, journal_path = _make_workspace(tmp_path)
    ctx = _make_ctx()
    _ZERO = "sha256:" + "0" * 64
    _ONE = "sha256:" + "1" * 64
    _TWO = "sha256:" + "2" * 64

    _journal_and_advance_seq(
        hashes={},
        before_hash=_ZERO,
        after_hash=_ONE,
        now="2026-06-01T00:00:00.000Z",
        state_path=state_path,
        journal_path=journal_path,
        ctx=ctx,
    )
    _journal_and_advance_seq(
        hashes={},
        before_hash=_ONE,
        after_hash=_TWO,
        now="2026-06-01T00:00:01.000Z",
        state_path=state_path,
        journal_path=journal_path,
        ctx=ctx,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["next_monotonic_seq"] == 2
    lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_journal_and_advance_seq_state_none_emits_error(tmp_path: Path) -> None:
    """_journal_and_advance_seq calls emit_error when state.json is missing."""
    import click

    from sdlc.cli.trust_hooks import _journal_and_advance_seq

    _, state_path, journal_path = _make_workspace(tmp_path)
    state_path.unlink()  # Remove state.json → read_state_or_recover returns None
    ctx = _make_ctx()
    _ZERO = "sha256:" + "0" * 64

    with pytest.raises((SystemExit, click.exceptions.Exit)):
        _journal_and_advance_seq(
            hashes={},
            before_hash=_ZERO,
            after_hash=_ZERO,
            now="2026-06-01T00:00:00.000Z",
            state_path=state_path,
            journal_path=journal_path,
            ctx=ctx,
        )


# ---------------------------------------------------------------------------
# run_trust_hooks — guard paths
# ---------------------------------------------------------------------------


def test_run_trust_hooks_exits_when_not_initialized(tmp_path: Path) -> None:
    """run_trust_hooks emits ERR_NOT_INITIALIZED when .claude/ is absent."""
    import click

    from sdlc.cli.trust_hooks import run_trust_hooks

    ctx = _make_ctx()
    with (
        patch("sdlc.cli.trust_hooks._get_repo_root_or_cwd", return_value=tmp_path),
        pytest.raises((SystemExit, click.exceptions.Exit)),
    ):
        run_trust_hooks(ctx=ctx)


def test_run_trust_hooks_happy_path_writes_hash_store(tmp_path: Path) -> None:
    """run_trust_hooks writes hook-hashes.json and advances state when workspace valid."""
    from sdlc.cli.trust_hooks import run_trust_hooks

    root, _state_path, _journal_path = _make_workspace(tmp_path)
    hooks_dir = root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    # Create a dummy hook file so compute_hook_hashes has something to hash.
    (hooks_dir / "pre_tool_use.py").write_text("# hook\n", encoding="utf-8")

    ctx = _make_ctx()
    with patch("sdlc.cli.trust_hooks._get_repo_root_or_cwd", return_value=root):
        run_trust_hooks(ctx=ctx)

    store = root / ".claude" / "state" / "hook-hashes.json"
    assert store.exists()
    data = json.loads(store.read_text(encoding="utf-8"))
    # hook-hashes.json format: {"schema_version": 1, "hashes": {<filename>: <sha256>}, ...}
    hashes = data.get("hashes", data)
    assert any("pre_tool_use" in k for k in hashes)


def test_run_trust_hooks_json_mode_emits_structured_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_trust_hooks emits JSON when ctx.obj['json'] is True."""
    from sdlc.cli.trust_hooks import run_trust_hooks

    root, _sp, _jp = _make_workspace(tmp_path)
    hooks_dir = root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = False
    ctx.obj["json"] = True

    with patch("sdlc.cli.trust_hooks._get_repo_root_or_cwd", return_value=root):
        run_trust_hooks(ctx=ctx)

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output.get("command") == "trust-hooks" or "project_root" in str(output)

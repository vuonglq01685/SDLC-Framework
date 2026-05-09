"""Unit tests for sdlc.cli.replay (Story 1.18, AC7.2)."""

from __future__ import annotations

import contextlib
import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import typer

from sdlc.cli.main import app
from sdlc.cli.replay import _parse_line_spec
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError

pytestmark = pytest.mark.unit

runner = __import__("typer.testing", fromlist=["CliRunner"]).CliRunner()


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def _make_entry(
    seq: int,
    ts: str,
    *,
    target_id: str = "state",
    actor: str = "cli",
    kind: str = "scan_completed",
    payload: dict[str, Any] | None = None,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=actor,
        kind=kind,
        target_id=target_id,
        before_hash=None if seq == 0 else "sha256:" + "0" * 64,
        after_hash="sha256:" + "1" * 64,
        payload=payload or {},
    )


def _bootstrap_project(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}")
    journal = state_dir / "journal.log"
    journal.touch()
    return journal


def _append_entry(journal: Path, entry: JournalEntry) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


# --- _parse_line_spec unit tests ---


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("42", (42, 42)),
        ("42-50", (42, 50)),
        ("42-42", (42, 42)),
        ("1", (1, 1)),
    ],
)
def test_replay_parse_line_spec_valid_forms(spec: str, expected: tuple[int, int]) -> None:
    assert _parse_line_spec(spec) == expected


@pytest.mark.parametrize(
    "spec",
    ["", "abc", "0", "-1", "5-", "-5", "50-42", "1-2-3", " ", "1.5", "1-2.5"],
)
def test_replay_parse_line_spec_invalid_forms(spec: str) -> None:
    with pytest.raises(JournalError):
        _parse_line_spec(spec)


# --- run_replay integration tests ---


def test_replay_refuses_when_state_not_initialized(tmp_path: Path) -> None:
    result = runner.invoke(app, ["replay", "1"], catch_exceptions=False)
    assert result.exit_code == 1


def test_replay_single_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(5):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:0{i}Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="3")
    stdout = out.getvalue()
    assert "--- line 3 ---" in stdout
    assert "monotonic_seq:" in stdout


def test_replay_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(10):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:{i:02d}Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="3-5")
    stdout = out.getvalue()
    assert "--- line 3 ---" in stdout
    assert "--- line 4 ---" in stdout
    assert "--- line 5 ---" in stdout
    assert "--- line 2 ---" not in stdout
    assert "--- line 6 ---" not in stdout


def test_replay_out_of_range_single(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(3):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:0{i}Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        replay.run_replay(ctx=ctx, line_spec="42")
    assert exc_info.value.exit_code == 1


def test_replay_out_of_range_range_partially_past_eof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(5):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:0{i}Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        replay.run_replay(ctx=ctx, line_spec="3-10")
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "not in journal" in captured.err


def test_replay_empty_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        replay.run_replay(ctx=ctx, line_spec="1")
    assert exc_info.value.exit_code == 1


def test_replay_range_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bootstrap_project(tmp_path)
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        replay.run_replay(ctx=ctx, line_spec="1-1001")
    assert exc_info.value.exit_code == 1


def test_replay_json_mode_envelope_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    for i in range(3):
        _append_entry(journal, _make_entry(i, f"2026-01-01T00:00:0{i}Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="1-3")
    payload = json.loads(out.getvalue())
    assert set(payload.keys()) == {"command", "lines", "line_count"}
    assert len(payload["lines"]) == 3


def test_replay_json_entry_field_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _bootstrap_project(tmp_path)
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx(json_mode=True)
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="1")
    payload = json.loads(out.getvalue())
    entry_fields = set(payload["lines"][0]["entry"].keys())
    expected = {
        "schema_version",
        "monotonic_seq",
        "ts",
        "actor",
        "kind",
        "target_id",
        "before_hash",
        "after_hash",
        "payload",
    }
    assert expected.issubset(entry_fields)


def test_replay_human_readable_includes_field_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _bootstrap_project(tmp_path)
    _append_entry(journal, _make_entry(0, "2026-01-01T00:00:00Z"))
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="1")
    stdout = out.getvalue()
    assert "monotonic_seq:" in stdout
    assert "kind:" in stdout
    assert "target_id:" in stdout
    assert "payload:" in stdout


def test_replay_human_readable_non_empty_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-empty payload fields are rendered as key: value lines."""
    journal = _bootstrap_project(tmp_path)
    _append_entry(
        journal,
        _make_entry(
            0,
            "2026-01-01T00:00:00Z",
            payload={"task_id": "EPIC-foo-S01-bar-T01-baz", "agent": "impl"},
        ),
    )
    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    ctx = _make_ctx()
    out = StringIO()
    with contextlib.redirect_stdout(out):
        replay.run_replay(ctx=ctx, line_spec="1")
    stdout = out.getvalue()
    assert "task_id:" in stdout
    assert "agent:" in stdout


def test_replay_journal_error_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JournalError during _read_journal_range → emit_error → exit."""
    import typing

    import sdlc.journal

    _bootstrap_project(tmp_path)

    def _raise_on_iter(*_a: typing.Any, **_kw: typing.Any) -> typing.Iterator[typing.Any]:
        raise JournalError("corrupted journal line")
        yield  # make it a generator

    from sdlc.cli import replay

    monkeypatch.setattr(replay, "get_repo_root_or_cwd", lambda: tmp_path)
    monkeypatch.setattr(sdlc.journal, "iter_entries", _raise_on_iter)
    ctx = _make_ctx()
    with pytest.raises(typer.Exit) as exc_info:
        replay.run_replay(ctx=ctx, line_spec="1")
    assert exc_info.value.exit_code in (1, 2)

"""Unit tests for sdlc.cli.output (Story 1.17, AC7.3)."""

from __future__ import annotations

import json

import pytest
import typer

from sdlc.cli.output import (
    _ANSI_RE,
    _ERR_CODE_TO_EXIT_CODE,
    _LOGS_OUTPUT_SCHEMA,
    _REPLAY_OUTPUT_SCHEMA,
    _TRACE_OUTPUT_SCHEMA,
    echo,
    emit_error,
    emit_json,
    is_no_color_active,
    make_console,
)

pytestmark = pytest.mark.unit


def _make_ctx(*, no_color: bool = False, json_mode: bool = False) -> typer.Context:
    """Build a minimal Typer context with obj dict."""
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json"] = json_mode
    return ctx


def test_echo_strips_ansi_when_no_color_active(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx(no_color=True)
    echo("\x1b[31merror\x1b[0m", ctx=ctx)
    captured = capsys.readouterr()
    assert _ANSI_RE.search(captured.out) is None
    assert "error" in captured.out


def test_echo_noop_in_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx(json_mode=True)
    echo("should not appear", ctx=ctx)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_echo_legacy_no_ctx(capsys: pytest.CaptureFixture[str]) -> None:
    echo("hello")
    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_emit_json_canonical_bytes(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx(json_mode=True)
    emit_json("test", {"foo": 1, "bar": 2}, ctx=ctx)
    captured = capsys.readouterr()
    assert captured.out.strip() == '{"bar":2,"command":"test","foo":1}'
    payload = json.loads(captured.out)
    assert payload["command"] == "test"
    assert payload["foo"] == 1
    assert payload["bar"] == 2


def test_emit_error_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit) as exc_info:
        emit_error("ERR_NOT_INITIALIZED", "test message", ctx=ctx)
    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["error"]["code"] == "ERR_NOT_INITIALIZED"
    assert envelope["error"]["message"] == "test message"
    assert envelope["error"]["exit_code"] == 1


def test_emit_error_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx()
    with pytest.raises(typer.Exit):
        emit_error("ERR_NOT_INITIALIZED", "test message", ctx=ctx)
    captured = capsys.readouterr()
    assert "test message" in captured.err
    assert captured.out == ""


def test_emit_error_scan_failed_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit) as exc_info:
        emit_error("ERR_SCAN_FAILED", "scanner error", ctx=ctx)
    assert exc_info.value.exit_code == 2


def test_is_no_color_active_respects_flag_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Flag set, env unset → True
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert is_no_color_active(_make_ctx(no_color=True)) is True

    # Flag unset, env set to "1" → True
    monkeypatch.setenv("NO_COLOR", "1")
    assert is_no_color_active(_make_ctx(no_color=False)) is True

    # Flag unset, env set to "" → False (empty = unset per no-color.org)
    monkeypatch.setenv("NO_COLOR", "")
    assert is_no_color_active(_make_ctx(no_color=False)) is False

    # Flag unset, env unset → False
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert is_no_color_active(_make_ctx(no_color=False)) is False

    # Flag set, env set → True (either disables)
    monkeypatch.setenv("NO_COLOR", "1")
    assert is_no_color_active(_make_ctx(no_color=True)) is True


def test_is_no_color_active_none_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert is_no_color_active(None) is False


@pytest.mark.parametrize(
    "code,expected_exit",
    [
        ("ERR_JOURNAL_READ_FAILED", 2),
        ("ERR_AGENT_RUNS_READ_FAILED", 2),
    ],
)
def test_emit_error_new_codes_map_to_exit_codes(code: str, expected_exit: int) -> None:
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit) as exc_info:
        emit_error(code, "test message", ctx=ctx)
    assert exc_info.value.exit_code == expected_exit


def test_emit_error_sanitizes_secret_patterns_in_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit):
        emit_error(
            "ERR_INFRASTRUCTURE",
            "infra error",
            ctx=ctx,
            details={"api_key": "sk-test-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
        )
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    # Secret value should be redacted (exact marker may vary — just assert it's not the raw value)
    raw_key = "sk-test-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    details = envelope["error"]["details"]
    assert details.get("api_key") != raw_key


def test_make_console_returns_rich_console() -> None:
    from rich.console import Console

    ctx = _make_ctx()
    console = make_console(ctx)
    assert isinstance(console, Console)


def test_make_console_cached_per_ctx() -> None:
    ctx = _make_ctx()
    c1 = make_console(ctx)
    c2 = make_console(ctx)
    assert c1 is c2


def test_err_code_to_exit_code_table() -> None:
    assert _ERR_CODE_TO_EXIT_CODE["ERR_NOT_INITIALIZED"] == 1
    assert _ERR_CODE_TO_EXIT_CODE["ERR_ALREADY_INITIALIZED"] == 1
    assert _ERR_CODE_TO_EXIT_CODE["ERR_SCAN_FAILED"] == 2
    assert _ERR_CODE_TO_EXIT_CODE["ERR_JOURNAL_APPEND_FAILED"] == 2
    assert _ERR_CODE_TO_EXIT_CODE["ERR_STATE_WRITE_FAILED"] == 2
    assert _ERR_CODE_TO_EXIT_CODE["ERR_INFRASTRUCTURE"] == 3


def test_output_schema_constants_are_v1() -> None:
    """B-P17: wire-format lock — all three story-1.18 schemas must be "v1"."""
    assert _TRACE_OUTPUT_SCHEMA == "v1"
    assert _REPLAY_OUTPUT_SCHEMA == "v1"
    assert _LOGS_OUTPUT_SCHEMA == "v1"


# ---------------------------------------------------------------------------
# Story 1.17 review additions: every ERR_* code's JSON envelope shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected_exit"),
    [
        ("ERR_NOT_INITIALIZED", 1),
        ("ERR_ALREADY_INITIALIZED", 1),
        ("ERR_USER_INPUT", 1),
        ("ERR_SCAN_FAILED", 2),
        ("ERR_JOURNAL_APPEND_FAILED", 2),
        ("ERR_STATE_WRITE_FAILED", 2),
        ("ERR_INFRASTRUCTURE", 3),
    ],
)
def test_emit_error_json_envelope_for_every_err_code(
    code: str, expected_exit: int, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every ERR_* code emits the canonical envelope with the right exit code."""
    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit) as exc_info:
        emit_error(code, f"{code} message", ctx=ctx, details={"k": "v"})
    assert exc_info.value.exit_code == expected_exit
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["error"]["code"] == code
    assert envelope["error"]["message"] == f"{code} message"
    assert envelope["error"]["exit_code"] == expected_exit
    assert envelope["error"]["details"] == {"k": "v"}


def test_emit_error_serializes_path_and_datetime_in_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path / datetime / set values in details are coerced (no TypeError crash)."""
    import datetime as _dt
    from pathlib import Path

    ctx = _make_ctx(json_mode=True)
    with pytest.raises(typer.Exit):
        emit_error(
            "ERR_INFRASTRUCTURE",
            "infra error",
            ctx=ctx,
            details={
                "path": Path("/tmp/sample"),
                "ts": _dt.datetime(2026, 5, 9, 12, 0, 0, tzinfo=_dt.timezone.utc),
                "tags": {"a", "b"},
            },
        )
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    details = envelope["error"]["details"]
    assert details["path"] == "/tmp/sample"
    assert details["ts"].startswith("2026-05-09T12:00:00")
    assert details["tags"] == ["a", "b"]


def test_emit_json_serializes_path_and_datetime() -> None:
    """emit_json coerces non-serializable values via canonical_dumps default=."""
    import datetime as _dt
    from pathlib import Path

    from sdlc.cli.output import canonical_dumps

    out = canonical_dumps(
        {
            "command": "demo",
            "p": Path("/x/y"),
            "t": _dt.date(2026, 5, 9),
            "s": frozenset({"b", "a"}),
        }
    )
    payload = json.loads(out)
    assert payload["p"] == "/x/y"
    assert payload["t"] == "2026-05-09"
    assert payload["s"] == ["a", "b"]

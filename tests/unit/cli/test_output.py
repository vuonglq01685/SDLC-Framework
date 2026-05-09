"""Unit tests for sdlc.cli.output (Story 1.17, AC7.3)."""

from __future__ import annotations

import json

import pytest
import typer

from sdlc.cli.output import (
    _ANSI_RE,
    _ERR_CODE_TO_EXIT_CODE,
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

"""CLI output helpers — Story 1.17 expanded surface.

Public API:
  echo(message, *, err, ctx)   — emit plain text; no-op in JSON mode; strips ANSI when --no-color.
  emit_json(command, payload, *, ctx) — emit canonical-bytes JSON document on stdout.
  emit_error(code, message, *, ctx, details) — emit error envelope; always raises typer.Exit.
  make_console(ctx)                 — lazy rich Console factory; caches per ctx.obj.
  is_no_color_active(ctx)           — True if --no-color flag OR NO_COLOR env is non-empty.

Error code → exit code table (_ERR_CODE_TO_EXIT_CODE):
  ERR_NOT_INITIALIZED    → 1
  ERR_ALREADY_INITIALIZED → 1
  ERR_USER_INPUT         → 1
  ERR_SCAN_FAILED        → 2
  ERR_JOURNAL_APPEND_FAILED → 2
  ERR_STATE_WRITE_FAILED → 2
  ERR_INFRASTRUCTURE     → 3
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NoReturn

import typer

from sdlc.config import sanitize_mapping

if TYPE_CHECKING:
    from rich.console import Console

__all__ = (  # noqa: RUF022
    "echo",
    "emit_json",
    "emit_error",
    "make_console",
    "is_no_color_active",
)

_ANSI_RE: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_NO_COLOR_ENV: Final[str] = "NO_COLOR"
_ERR_CODE_TO_EXIT_CODE: Final[Mapping[str, int]] = MappingProxyType(
    {
        "ERR_NOT_INITIALIZED": 1,
        "ERR_ALREADY_INITIALIZED": 1,
        "ERR_USER_INPUT": 1,
        "ERR_SCAN_FAILED": 2,
        "ERR_JOURNAL_APPEND_FAILED": 2,
        "ERR_STATE_WRITE_FAILED": 2,
        "ERR_INFRASTRUCTURE": 3,
    }
)
_DEFAULT_EXIT_CODE: Final[int] = 1
_SCAN_OUTPUT_SCHEMA: Final[str] = "v1"
_STATUS_OUTPUT_SCHEMA: Final[str] = "v1"


def is_no_color_active(ctx: typer.Context | None) -> bool:
    """True if --no-color flag is set OR NO_COLOR env is non-empty."""
    flag = bool(ctx is not None and ctx.obj is not None and ctx.obj.get("no_color", False))
    env = os.environ.get(_NO_COLOR_ENV, "") != ""
    return flag or env


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def echo(message: str, *, err: bool = False, ctx: typer.Context | None = None) -> None:
    """Emit ``message`` on stdout (or stderr if err=True).

    - If ctx.obj["json"] is True: NO-OP (JSON mode silences plain channels).
    - If is_no_color_active(ctx): strip ANSI before emission.
    - Otherwise: forward to typer.echo verbatim.
    Backward-compat: when ctx is None (legacy callers), behavior matches Story 1.16's stub.
    """
    if ctx is not None and ctx.obj is not None and ctx.obj.get("json", False):
        return
    if is_no_color_active(ctx):
        message = _strip_ansi(message)
    typer.echo(message, err=err)


def emit_json(command: str, payload: Mapping[str, object], *, ctx: typer.Context) -> None:
    """Emit canonical-bytes JSON document on stdout.

    Schema: payload is augmented with command field; sorted keys, no ascii escaping,
    compact separators, trailing newline (matches state.atomic canonical-bytes contract).
    """
    merged: dict[str, object] = dict(payload)
    merged.setdefault("command", command)
    canonical = json.dumps(merged, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    typer.echo(canonical)


def emit_error(
    code: str,
    message: str,
    *,
    ctx: typer.Context,
    details: Mapping[str, object] | None = None,
) -> NoReturn:
    """Emit error envelope per Architecture §549; raise typer.Exit with mapped code.

    - JSON mode: stderr gets {"error": {code, message, details, exit_code}} canonical bytes.
    - Default mode: stderr gets a plain-text "sdlc: <message>" line.
    Precedence for --no-color: checked in default mode for plain-text output.
    """
    exit_code = _ERR_CODE_TO_EXIT_CODE.get(code, _DEFAULT_EXIT_CODE)
    json_mode = bool(ctx.obj is not None and ctx.obj.get("json", False))
    if json_mode:
        safe_details: dict[str, object] = sanitize_mapping(dict(details)) if details else {}
        envelope = {
            "error": {
                "code": code,
                "message": message,
                "details": safe_details,
                "exit_code": exit_code,
            }
        }
        canonical = json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        typer.echo(canonical, err=True)
    else:
        text = f"sdlc: {message}"
        if is_no_color_active(ctx):
            text = _strip_ansi(text)
        typer.echo(text, err=True)
    raise typer.Exit(code=exit_code)


def make_console(ctx: typer.Context) -> Console:
    """Lazy rich Console factory; caches per ctx.obj.

    Deferred rich import keeps the --version cold-start budget under 200 ms
    (Architecture §488); rich is imported only when a command actually styles output.
    """
    if ctx.obj is None:
        ctx.ensure_object(dict)
    cached = ctx.obj.get("_console")
    if cached is not None:
        from rich.console import Console

        assert isinstance(cached, Console)
        return cached
    from rich.console import Console  # deferred per Architecture §488

    no_color = is_no_color_active(ctx)
    console = Console(no_color=no_color, force_terminal=False)
    ctx.obj["_console"] = console
    return console

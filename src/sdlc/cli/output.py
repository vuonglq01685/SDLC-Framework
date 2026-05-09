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
  ERR_JOURNAL_READ_FAILED → 2    (Story 1.18)
  ERR_AGENT_RUNS_READ_FAILED → 2 (Story 1.18)
  ERR_MIGRATION_NOT_FOUND → 2   (Story 1.19)
  ERR_MIGRATION_INVALID → 2     (Story 1.19)
  ERR_MIGRATION_FAILED → 2      (Story 1.19)
  ERR_MIGRATION_DOWNGRADE → 2   (Story 1.19)
  ERR_STATE_MALFORMED → 2       (Story 1.19)
  ERR_NO_RECOVERY_SOURCE → 2   (Story 1.20)
  ERR_JOURNAL_CORRUPT → 2      (Story 1.20)
  ERR_JOURNAL_SCHEMA_DRIFT → 2 (Story 1.20)

Per-command JSON output schemas (Story 1.21 wire-format-lock ceremony freezes these at v1):
  _SCAN_OUTPUT_SCHEMA, _STATUS_OUTPUT_SCHEMA, _TRACE_OUTPUT_SCHEMA,
  _REPLAY_OUTPUT_SCHEMA, _LOGS_OUTPUT_SCHEMA

Story 1.18 extension: adds ERR_JOURNAL_READ_FAILED, ERR_AGENT_RUNS_READ_FAILED;
declares _TRACE_OUTPUT_SCHEMA, _REPLAY_OUTPUT_SCHEMA, _LOGS_OUTPUT_SCHEMA constants.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from collections.abc import Mapping
from pathlib import PurePath
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
    "canonical_dumps",
)


def _json_default(obj: object) -> object:
    """JSON `default=` handler that coerces common non-serializable types.

    Path / datetime / set / frozenset are stringified or listified so the
    canonical JSON envelope never crashes on detail dicts that contain
    them. Anything still unsupported raises TypeError as usual — that's
    the right signal for a bug, not a runtime envelope failure.
    """
    if isinstance(obj, PurePath):
        return obj.as_posix()
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=str)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def canonical_dumps(payload: Mapping[str, object]) -> str:
    """Canonical JSON dumps used by every CLI emitter.

    sort_keys=True, ensure_ascii=False, compact separators, default= coerces
    Path/datetime/set. One source of truth for the wire format so emit_json,
    emit_error, and the version eager-callback cannot drift.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
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
        # Added in Story 1.18 — see ADR-021.
        "ERR_JOURNAL_READ_FAILED": 2,
        "ERR_AGENT_RUNS_READ_FAILED": 2,
        # Added in Story 1.19 — see ADR-022.
        "ERR_MIGRATION_NOT_FOUND": 2,
        "ERR_MIGRATION_INVALID": 2,
        "ERR_MIGRATION_FAILED": 2,
        "ERR_MIGRATION_DOWNGRADE": 2,
        "ERR_STATE_MALFORMED": 2,
        # Added in Story 1.20 — see ADR-023.
        "ERR_NO_RECOVERY_SOURCE": 2,
        "ERR_JOURNAL_CORRUPT": 2,
        "ERR_JOURNAL_SCHEMA_DRIFT": 2,
    }
)
_DEFAULT_EXIT_CODE: Final[int] = 1
_SCAN_OUTPUT_SCHEMA: Final[str] = "v1"
_STATUS_OUTPUT_SCHEMA: Final[str] = "v1"
_TRACE_OUTPUT_SCHEMA: Final[str] = "v1"
_REPLAY_OUTPUT_SCHEMA: Final[str] = "v1"
_LOGS_OUTPUT_SCHEMA: Final[str] = "v1"


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
    Non-serializable values (Path, datetime, set) are coerced via canonical_dumps.
    """
    merged: dict[str, object] = dict(payload)
    merged.setdefault("command", command)
    typer.echo(canonical_dumps(merged))


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
        typer.echo(canonical_dumps(envelope), err=True)
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

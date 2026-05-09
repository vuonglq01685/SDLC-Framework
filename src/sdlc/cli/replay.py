"""`sdlc replay <line-or-range>` implementation (FR34, Architecture §804, §1160).

Pretty-prints parsed JournalEntry models.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd
from sdlc.cli.output import emit_error, emit_json, make_console
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.errors import JournalError

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_MAX_REPLAY_RANGE: Final[int] = 1000
_SINGLE_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^([1-9]\d*)$")
_RANGE_RE: Final[re.Pattern[str]] = re.compile(r"^([1-9]\d*)-([1-9]\d*)$")


def _parse_line_spec(spec: str) -> tuple[int, int]:
    """Parse 'N' or 'N-M'. Both 1-indexed inclusive; require start ≤ end.

    Raises JournalError on any invalid form (caller maps to ERR_USER_INPUT exit 1).
    """
    if not spec or not spec.strip():
        raise JournalError(
            "invalid replay spec: empty",
            details={"input": spec, "rule": "empty"},
        )
    m_single = _SINGLE_LINE_RE.match(spec)
    if m_single is not None:
        n = int(m_single.group(1))
        return (n, n)
    m_range = _RANGE_RE.match(spec)
    if m_range is None:
        raise JournalError(
            f"invalid replay spec: {spec!r} "
            "(must be 'N' or 'N-M' with 1-indexed positive integers)",
            details={"input": spec, "rule": "invalid_shape"},
        )
    start = int(m_range.group(1))
    end = int(m_range.group(2))
    if start > end:
        raise JournalError(
            f"replay spec start must be ≤ end (got {start}-{end})",
            details={"input": spec, "rule": "inverted_range", "start": start, "end": end},
        )
    if (end - start + 1) > _MAX_REPLAY_RANGE:
        raise JournalError(
            f"replay range too large ({end - start + 1} lines requested; max {_MAX_REPLAY_RANGE})",
            details={
                "input": spec,
                "rule": "range_too_large",
                "requested": end - start + 1,
                "max": _MAX_REPLAY_RANGE,
            },
        )
    return (start, end)


def _format_payload_value(v: Any) -> str:
    """Stringify a payload value as JSON-ish for human display.

    Bytes/dicts/lists round-trip through json.dumps with default=str so
    nested structures stay readable instead of falling back to Python repr.
    """
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(v)


def _format_entry_human(lineno: int, entry: JournalEntry) -> list[str]:
    """Return a list of lines forming the pretty-print block for one entry."""
    lines = [f"--- line {lineno} ---"]
    lines.append(f"monotonic_seq:  {entry.monotonic_seq}")
    lines.append(f"ts:             {entry.ts}")
    lines.append(f"actor:          {entry.actor}")
    lines.append(f"kind:           {entry.kind}")
    lines.append(f"target_id:      {entry.target_id}")
    lines.append(f"before_hash:    {entry.before_hash}")
    lines.append(f"after_hash:     {entry.after_hash}")
    lines.append("payload:")
    if entry.payload:
        for k, v in entry.payload.items():
            lines.append(f"  {k}: {_format_payload_value(v)}")
    else:
        lines.append("  (empty)")
    return lines


def _read_journal_range(
    journal_path: Path,
    start: int,
    end: int,
    *,
    ctx: typer.Context,
) -> list[tuple[int, JournalEntry]]:
    """Read journal entries in [start, end] (1-indexed inclusive).

    Emits ERR_USER_INPUT and raises typer.Exit if any line is out of range.
    """
    from sdlc.journal import iter_entries  # deferred

    # Distinguish "journal log file does not exist yet" from "journal exists but
    # has 0 lines" — both fail AC3.3 but the missing-file case deserves a clearer
    # diagnostic so users running `sdlc replay 1` against a fresh project see
    # what is wrong without rummaging through the filesystem.
    if not journal_path.exists():
        emit_error(
            "ERR_USER_INPUT",
            f"line {end} not in journal (journal log not found at {journal_path})",
            ctx=ctx,
            details={
                "requested_line": end,
                "journal_lines": 0,
                "path": str(journal_path),
                "exists": False,
            },
        )

    collected: list[tuple[int, JournalEntry]] = []
    total_lines = 0
    try:
        for lineno, entry in enumerate(iter_entries(journal_path), start=1):
            total_lines = lineno
            if start <= lineno <= end:
                collected.append((lineno, entry))
            if lineno >= end and len(collected) == (end - start + 1):
                break
    except JournalError as exc:
        emit_error(
            "ERR_JOURNAL_READ_FAILED",
            f"journal read failed: {exc.message}",
            ctx=ctx,
            details=dict(exc.details),
        )

    if end > total_lines:
        emit_error(
            "ERR_USER_INPUT",
            f"line {end} not in journal (journal has {total_lines} lines)",
            ctx=ctx,
            details={
                "requested_line": end,
                "journal_lines": total_lines,
                "path": str(journal_path),
            },
        )
    return collected


def run_replay(*, ctx: typer.Context, line_spec: str) -> None:
    """Pretty-print parsed journal entries by line number or range."""
    root = get_repo_root_or_cwd()
    if not (root / _STATE_PATH_REL).exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    try:
        start, end = _parse_line_spec(line_spec)
    except JournalError as exc:
        emit_error(
            "ERR_USER_INPUT",
            exc.message,
            ctx=ctx,
            details=dict(exc.details),
        )

    journal_path = root / _JOURNAL_PATH_REL
    collected = _read_journal_range(journal_path, start, end, ctx=ctx)

    if ctx.obj.get("json", False):
        emit_json(
            "replay",
            {
                "lines": [
                    {"lineno": ln, "entry": entry.model_dump(mode="json")}
                    for ln, entry in collected
                ],
                "line_count": len(collected),
            },
            ctx=ctx,
        )
        return

    console = make_console(ctx)
    for ln, entry in collected:
        console.rule(f"line {ln}")
        console.print(f"monotonic_seq:  {entry.monotonic_seq}")
        console.print(f"ts:             [dim]{entry.ts}[/dim]")
        console.print(f"actor:          {entry.actor}")
        console.print(f"[bold]kind:[/bold]           [bold]{entry.kind}[/bold]")
        console.print(f"target_id:      {entry.target_id}")
        console.print(f"[dim]before_hash:    {entry.before_hash}[/dim]")
        console.print(f"[dim]after_hash:     {entry.after_hash}[/dim]")
        console.print("payload:")
        if entry.payload:
            for k, v in entry.payload.items():
                console.print(f"  {k}: {_format_payload_value(v)}")
        else:
            console.print("  (empty)")

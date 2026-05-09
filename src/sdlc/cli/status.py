"""`sdlc status` implementation (FR44, Architecture §801, §1170).

Read-only resume card; projects state + last journal entry. NO writes to
state.json or journal.log. Tests verify zero writes via mtime-snapshot.
"""

from __future__ import annotations

import datetime
import logging
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import echo, emit_error, emit_json

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_PHASE_NAMES: Final[Mapping[int, str]] = MappingProxyType(
    {1: "Requirement", 2: "Architecture", 3: "Implementation"}
)
_NEVER_SENTINEL: Final[str] = "<never - run `sdlc scan`>"
_PYPROJECT_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE
)


def _resolve_project_name(root: Path) -> str:
    """Best-effort project name from pyproject.toml [project] name; fallback to dir basename.

    Uses tomllib (Python 3.11+) for proper TOML parsing when available; falls back to
    a regex on the [project] section for Python 3.10 (per AC2.1).
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return root.name
    if sys.version_info >= (3, 11):
        return _resolve_via_tomllib(pyproject, root.name)
    return _resolve_via_regex(pyproject, root.name)


def _resolve_via_tomllib(pyproject: Path, fallback_name: str) -> str:
    """Python 3.11+ path: parse pyproject.toml with tomllib and read `[project] name`."""
    import tomllib  # type: ignore[import-not-found]  # 3.11+ stdlib; mypy targets 3.10

    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return fallback_name
    project = data.get("project")
    if isinstance(project, Mapping):
        name = project.get("name")
        if isinstance(name, str) and name:
            return name
    return fallback_name


def _resolve_via_regex(pyproject: Path, fallback_name: str) -> str:
    """Python 3.10 fallback: regex on the [project] section only.

    Avoids matching `name = ...` under `[tool.poetry]` or other tables that
    appear earlier in the file. Exposed as a separate function so it can be
    unit-tested on Python 3.11+ without monkey-patching sys.version_info.
    """
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return fallback_name
    project_section = _extract_project_section(text)
    if project_section is None:
        return fallback_name
    m = _PYPROJECT_NAME_RE.search(project_section)
    if m:
        return m.group(1)
    return fallback_name


def _extract_project_section(text: str) -> str | None:
    """Return the body of the `[project]` table from a pyproject.toml text, or None."""
    in_project = False
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[project]":
                in_project = True
                continue
            if in_project:
                # next table starts; stop
                break
            continue
        if in_project:
            body.append(line)
    return "\n".join(body) if in_project else None


def _get_last_journal_ts(journal_path: Path) -> str | None:
    """Return the latest entry's ts (RFC 3339 UTC string) or None for empty/missing journal."""
    from sdlc.journal import iter_entries  # deferred

    if not journal_path.exists():
        return None
    last_ts: str | None = None
    for entry in iter_entries(journal_path):
        last_ts = entry.ts
    return last_ts


def _format_ts_local(ts: str) -> str:
    """RFC 3339 UTC string -> local-timezone human string. 3.10-compatible.

    Returns the raw `ts` string on any parse or conversion failure (AC2.6: status is
    informational and never errors regardless of state shape).
    """
    normalized = ts.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(normalized)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError, OSError):
        return ts


def _compute_suggested_next(state) -> str:  # type: ignore[no-untyped-def]
    """Minimal v1.17 stub. Story 4.x's auto_loop owns the rich engine.
    Fresh-project case is the only AC-tested branch.
    """
    # v1.17 stub — Story 4.x's auto_loop owns the rich suggestion engine.
    phase = getattr(state, "phase", 1)
    if phase == 1 and not state.epics:
        return '/sdlc-start "<idea>"'
    return "sdlc scan"


def run_status(*, ctx: typer.Context) -> None:
    """Print the resume card with suggested next-action (FR44). Read-only."""
    from sdlc.errors import StateError
    from sdlc.state import read_state

    root = _get_repo_root_or_cwd()
    state_path = root / _STATE_PATH_REL
    journal_path = root / _JOURNAL_PATH_REL

    if not state_path.exists():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    try:
        state = read_state(state_path)
    except StateError as exc:
        emit_error(
            "ERR_INFRASTRUCTURE",
            f"failed to read state.json: {exc}",
            ctx=ctx,
            details={"path": str(state_path)},
        )
    if state is None:
        # TOCTOU: state_path.exists() was true above. Treat as not initialized.
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    project_name = _resolve_project_name(root)
    phase = getattr(state, "phase", 1)
    phase_name = _PHASE_NAMES.get(phase)
    if phase_name is None:
        _logger.warning("status: unknown phase %d (no name in _PHASE_NAMES)", phase)
        phase_name = "unknown"
    last_ts_raw = _get_last_journal_ts(journal_path)
    suggested_next = _compute_suggested_next(state)

    if ctx.obj is not None and ctx.obj.get("json", False):
        emit_json(
            "status",
            {
                "project_name": project_name,
                "project_root": str(root),
                "phase": phase,
                "phase_name": phase_name,
                "last_updated_ts": last_ts_raw,
                "epic_count": len(state.epics),
                "story_count": len(state.stories) if hasattr(state, "stories") else 0,
                "task_count": len(state.tasks) if hasattr(state, "tasks") else 0,
                "suggested_next": suggested_next,
                "next_monotonic_seq": state.next_monotonic_seq,
            },
            ctx=ctx,
        )
        return

    last_ts_display = _format_ts_local(last_ts_raw) if last_ts_raw else _NEVER_SENTINEL
    echo(f"sdlc status — {project_name}", ctx=ctx)
    echo(f"Phase: {phase} ({phase_name})", ctx=ctx)
    echo(f"Last updated: {last_ts_display}", ctx=ctx)
    echo(f"Suggested next: {suggested_next}", ctx=ctx)
    echo("---", ctx=ctx)

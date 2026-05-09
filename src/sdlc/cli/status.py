"""`sdlc status` implementation (FR44, Architecture §801, §1170).

Read-only resume card; projects state + last journal entry. NO writes to
state.json or journal.log. Tests verify zero writes via mtime-snapshot.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer

from sdlc.cli.output import echo, emit_error, emit_json

_logger = logging.getLogger(__name__)

_STATE_PATH_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_PATH_REL: Final[str] = ".claude/state/journal.log"
_PHASE_NAMES: Final[Mapping[int, str]] = MappingProxyType(
    {1: "Requirement", 2: "Architecture", 3: "Implementation"}
)
_NEVER_SENTINEL: Final[str] = "<never — run `sdlc scan`>"
_PYPROJECT_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r'^name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE
)
_GIT_TIMEOUT_SECONDS: Final[float] = 30.0


def _get_repo_root_or_cwd() -> Path:
    """Return the git repo root, falling back to cwd if git is absent or unavailable."""
    cwd = Path.cwd().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            cwd=cwd,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top).resolve()
    except (OSError, subprocess.SubprocessError, FileNotFoundError):
        pass
    return cwd


def _resolve_project_name(root: Path) -> str:
    """Best-effort project name from pyproject.toml [project] name; fallback to dir basename."""
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return root.name
        m = _PYPROJECT_NAME_RE.search(text)
        if m:
            return m.group(1)
    return root.name


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
    """RFC 3339 UTC string → local-timezone human string. 3.10-compatible."""
    normalized = ts.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return ts
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S %Z")


def _read_state_portable(state_path: Path) -> State:  # type: ignore[name-defined]  # noqa: F821
    """Read state.json portably without POSIX-only read_state dependency."""
    from sdlc.errors import StateError
    from sdlc.state import State

    try:
        text = state_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        return State.model_validate(payload)
    except json.JSONDecodeError as e:
        raise StateError(
            f"state.json contains invalid JSON: {e}",
            details={"path": str(state_path), "reason": "json"},
        ) from e
    except (ValueError, TypeError) as e:
        raise StateError(
            f"state.json failed schema validation: {e}",
            details={"path": str(state_path), "reason": "schema"},
        ) from e


def _compute_suggested_next(state: State) -> str:  # type: ignore[name-defined]  # noqa: F821
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
        state = _read_state_portable(state_path)
    except (OSError, StateError) as exc:
        emit_error(
            "ERR_STATE_WRITE_FAILED",
            f"failed to read state.json: {exc}",
            ctx=ctx,
            details={"path": str(state_path)},
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

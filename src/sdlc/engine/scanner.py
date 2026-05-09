"""Filesystem scanner for SDLC projects (FR3, Architecture §815, §1133, Decision A4 + B5).

Pure read-only function: walks `01-Requirement/04-Epics/`, `01-Requirement/05-Stories/`,
`03-Implementation/tasks/`; returns a `State` projection. NO writes — `cli/scan.py`
(Story 1.17) handles state.json + journal append.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from sdlc.errors import IdsError, StateError
from sdlc.ids import (
    EPIC_ID_REGEX,
    STORY_ID_REGEX,
    TASK_ID_REGEX,
    parse_epic_id,
    parse_story_id,
    parse_task_id,
)
from sdlc.state import State

_logger = logging.getLogger(__name__)

_EPICS_SUBDIR: Final[str] = "01-Requirement/04-Epics"
_STORIES_SUBDIR: Final[str] = "01-Requirement/05-Stories"
_TASKS_SUBDIR: Final[str] = "03-Implementation/tasks"

_IdParser = Callable[[str], Any]


def _validate_project_root(project_root: Path) -> None:
    if not project_root.is_absolute():
        raise StateError(
            "scan requires an absolute project_root path",
            details={"path": str(project_root), "reason": "not_absolute"},
        )
    if not project_root.exists():
        raise StateError(
            "scan target does not exist",
            details={"path": str(project_root), "reason": "not_found"},
        )
    if not project_root.is_dir():
        raise StateError(
            "scan project_root points at a non-directory path",
            details={"path": str(project_root), "reason": "not_a_directory"},
        )


def _rel(path: Path, project_root: Path) -> str:
    """Return path relative to project_root for error envelopes (AC1 contract)."""
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _load_json_artifact(path: Path, project_root: Path) -> dict[str, Any]:
    try:
        # utf-8-sig accepts UTF-8 with or without BOM (Notepad-saved artifacts).
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StateError(
            f"scan failed to decode artifact as UTF-8: {exc}",
            details={"file": _rel(path, project_root), "reason": "non_utf8_artifact"},
        ) from exc
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateError(
            f"scan failed to parse JSON artifact: {exc}",
            details={"file": _rel(path, project_root), "reason": "malformed_artifact"},
        ) from exc
    if not isinstance(result, dict):
        raise StateError(
            "scan expected JSON object at top level",
            details={"file": _rel(path, project_root), "reason": "non_object_artifact"},
        )
    return cast(dict[str, Any], result)


def _is_inside(child: Path, ancestor: Path) -> bool:
    """Return True iff child resolves to a descendant of ancestor.

    Uses resolve() to follow symlinks, then explicit string-prefix comparison
    (Path.is_relative_to is 3.9+ and works, but the prefix form is identical
    semantically and slightly faster on hot scan paths).
    """
    try:
        resolved = child.resolve()
        return resolved == ancestor or ancestor in resolved.parents
    except OSError:
        return False


def _classify_walk_entry(
    p: Path, regex: re.Pattern[str], project_root: Path, dir_path: Path
) -> bool:
    """Return True if p should be included in the walk; False otherwise.

    Logs INFO/WARNING for skipped entries with rationale. Pure side-effect
    isolation keeps `_walk_dir_sorted` under the mccabe complexity cap.
    """
    if not p.is_file():
        if p.is_symlink() and not p.exists():
            _logger.info("scan: skipping broken symlink %s under %s", p.name, dir_path)
        return False
    if p.name.startswith(".") or p.suffix != ".json":
        return False
    if not regex.match(p.stem):
        _logger.warning(
            "scan: skipping foreign filename %s under %s (does not match %s)",
            p.name,
            dir_path,
            regex.pattern,
        )
        return False
    if not _is_inside(p, project_root):
        _logger.warning(
            "scan: skipping artifact %s under %s — resolves outside project_root",
            p.name,
            dir_path,
        )
        return False
    return True


def _walk_dir_sorted(dir_path: Path, regex: re.Pattern[str], project_root: Path) -> list[Path]:
    """Return sorted .json file paths under dir_path whose stems match regex.

    Non-matching stems are logged at WARNING and skipped (never raised).
    Hidden files (leading '.') and non-.json files are silently skipped.
    Broken symlinks are logged at INFO and skipped (AC2 contract).

    Symlinks resolving outside `project_root` are logged at WARNING and
    skipped — defense-in-depth against an artifact pointing at sensitive
    files outside the project tree.
    """
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda x: x.name)
    except (PermissionError, OSError) as exc:
        _logger.warning(
            "scan: cannot enumerate %s (%s); skipping",
            dir_path,
            exc,
        )
        return []
    return [p for p in entries if _classify_walk_entry(p, regex, project_root, dir_path)]


def _load_artifacts_from_dir(
    dir_path: Path,
    file_regex: re.Pattern[str],
    parse_id: _IdParser,
    kind: str,
    project_root: Path,
) -> dict[str, Any]:
    """Load all JSON artifacts from a flat directory, keyed by canonical id."""
    artifacts: dict[str, Any] = {}
    for path in _walk_dir_sorted(dir_path, file_regex, project_root):
        try:
            payload = _load_json_artifact(path, project_root)
        except (OSError, PermissionError) as exc:
            # File vanished/unreadable between iterdir() and read_text() — skip
            # with WARN. Consistent with v1's "permissive scanner" stance (AC1.2).
            _logger.warning(
                "scan: artifact disappeared during scan: %s (%s)",
                _rel(path, project_root),
                exc,
            )
            continue
        try:
            artifact_id: str = parse_id(path.stem).raw
        except IdsError as exc:
            raise StateError(
                f"scan failed to parse {kind} id: {exc}",
                details={"file": _rel(path, project_root), "reason": "malformed_artifact"},
            ) from exc
        artifacts[artifact_id] = payload
    return artifacts


def _load_nested_artifacts(
    parent: Path,
    subdir_regex: re.Pattern[str],
    file_regex: re.Pattern[str],
    parse_id: _IdParser,
    kind: str,
    project_root: Path,
) -> dict[str, Any]:
    """Load JSON artifacts from subdirs of parent, skipping non-matching subdir names."""
    artifacts: dict[str, Any] = {}
    if not parent.exists() or not parent.is_dir():
        return artifacts
    try:
        subdirs = sorted(parent.iterdir(), key=lambda p: p.name)
    except (PermissionError, OSError) as exc:
        _logger.warning(
            "scan: cannot enumerate %s (%s); skipping",
            parent,
            exc,
        )
        return artifacts
    for subdir in subdirs:
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        if not subdir_regex.match(subdir.name):
            _logger.info("scan: skipping directory %s under %s/", subdir.name, parent.name)
            continue
        if not _is_inside(subdir, project_root):
            _logger.warning(
                "scan: skipping subdir %s under %s — resolves outside project_root",
                subdir.name,
                parent,
            )
            continue
        artifacts.update(_load_artifacts_from_dir(subdir, file_regex, parse_id, kind, project_root))
    return artifacts


def scan(project_root: Path) -> State:
    """Scan the project artifact tree and return a deterministic State projection.

    Pure: zero filesystem writes, zero journal appends, zero subprocess calls.
    Total: returns a valid State for every reachable input (empty, partial, full).
    Deterministic: two back-to-back calls on the same on-disk state produce
    model_dump(mode="json")-byte-equal results.

    Raises StateError when project_root is not absolute, does not exist, is a
    file, or a discovered artifact contains invalid JSON / non-UTF-8 bytes /
    a non-object JSON root. Missing layout directories within an existing
    project_root are treated as empty (not an error).
    """
    _validate_project_root(project_root)
    # Resolve once so the symlink-sandbox check (`_is_inside`) compares
    # canonical absolute paths rather than user-supplied surface paths.
    project_root = project_root.resolve()

    epics_dict = dict(
        sorted(
            _load_artifacts_from_dir(
                project_root / _EPICS_SUBDIR,
                EPIC_ID_REGEX,
                parse_epic_id,
                "epic",
                project_root,
            ).items()
        )
    )
    stories_dict = dict(
        sorted(
            _load_nested_artifacts(
                project_root / _STORIES_SUBDIR,
                EPIC_ID_REGEX,
                STORY_ID_REGEX,
                parse_story_id,
                "story",
                project_root,
            ).items()
        )
    )
    tasks_dict = dict(
        sorted(
            _load_nested_artifacts(
                project_root / _TASKS_SUBDIR,
                STORY_ID_REGEX,
                TASK_ID_REGEX,
                parse_task_id,
                "task",
                project_root,
            ).items()
        )
    )

    return State(
        schema_version=1,
        next_monotonic_seq=0,
        phase=1,
        epics=epics_dict,
        stories=stories_dict,
        tasks=tasks_dict,
    )

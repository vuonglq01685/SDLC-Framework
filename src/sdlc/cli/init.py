"""`sdlc init` (greenfield) implementation (FR1, Architecture §1131, §443).

Scaffolds the canonical SDLC layout: `.claude/state/`,
`.claude/{agents,commands,hooks,workflows,memory,skills}/`,
`01-Requirement/`, `02-Architecture/`, `03-Implementation/`.

Idempotent-via-refusal: re-running on an already-initialized repo exits 1
without overwriting (AC3).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from importlib.resources import files as _resource_files

# importlib.resources.abc.Traversable landed in 3.11; fall back to importlib.abc
# for 3.10. The fallback path is only exercised on 3.10; on 3.11+ the primary
# import always succeeds and the deprecated alias under importlib.abc never
# loads (avoids DeprecationWarning that pytest filterwarnings=["error"]
# promotes to a hard error).
try:
    from importlib.resources.abc import Traversable  # type: ignore[import-not-found]
except ImportError:
    from importlib.abc import Traversable
from pathlib import Path
from typing import Final

import typer

from sdlc.cli.exit_codes import EXIT_USER_ERROR
from sdlc.cli.output import echo

_logger = logging.getLogger(__name__)

_CLAUDE_DIR: Final[str] = ".claude"
_STATE_SUBDIR: Final[str] = ".claude/state"
_STATIC_ASSET_TREES: Final[tuple[str, ...]] = (
    "agents",
    "commands",
    "hooks",
    "workflows",
    "memory",
    "skills",
)
_PHASE_DIRS: Final[tuple[str, ...]] = (
    "01-Requirement",
    "02-Architecture",
    "03-Implementation",
)
_ALREADY_INITIALIZED_TEMPLATE: Final[str] = (
    "sdlc: already initialized at {root}; use `sdlc scan` to refresh state.json"
)
# Cold CI agents legitimately exceed 5s when git is invoked from a deep tree
# or under heavy I/O contention. 30s is the same ceiling used by uv / pre-commit.
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


def _state_already_exists(root: Path) -> bool:
    """Return True if a prior init artifact exists — the canonical re-init signal.

    Checks both `state.json` (canonical signal) and `journal.log` (partial-layout
    signal: a prior run created the state subtree but crashed before writing
    state.json). Either one triggers the idempotent-via-refusal contract.
    """
    state_dir = root / ".claude" / "state"
    return (state_dir / "state.json").exists() or (state_dir / "journal.log").exists()


def _canonical_initial_state_bytes() -> bytes:
    """Canonical bytes for the empty initial State (Story 1.10/1.15 schema).

    Follows the canonical-bytes contract from `state/atomic.py`: sort_keys,
    no ASCII escaping, compact separators, trailing newline.
    """
    from sdlc.state import State  # deferred per Architecture §488

    payload = State().model_dump(mode="json")
    return (
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_state_json_windows_atomic(state_path: Path) -> None:
    """Windows-only atomic write: temp file in the same directory + os.replace().

    Mirrors the POSIX atomic protocol (Architecture §573) on NTFS. `os.replace`
    is atomic on the same volume, so a crash mid-write leaves either the old
    file (here: nothing) or the new fully-written file — never a partial.
    Story 1.20 owns full crash-recovery; this closes the half-write window.
    """
    payload = _canonical_initial_state_bytes()
    parent = state_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=str(parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, state_path)  # noqa: state-write -- Windows atomic equivalent of POSIX protocol
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def _write_state_json(state_path: Path) -> None:
    """Write the canonical initial state.json.

    Uses `state.write_state_atomic_sync` on POSIX; on Windows uses a temp-file
    + `os.replace()` shim that mirrors the POSIX atomic semantics on NTFS
    (the underlying `state.atomic` module is POSIX-only — fcntl + parent-dir
    fsync — per pyproject.toml omit list and Architecture §573).
    """
    if sys.platform == "win32":
        _write_state_json_windows_atomic(state_path)
        return
    from sdlc.state import State, write_state_atomic_sync  # deferred

    write_state_atomic_sync(State(), target=state_path)


def _create_state_subtree(root: Path) -> None:
    state_dir = root / _STATE_SUBDIR
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_state_json(state_dir / "state.json")
    (state_dir / "journal.log").touch()


def _safe_child_name(name: str) -> bool:
    """Reject child names that could traverse out of the destination tree.

    Defense-in-depth against malformed package_data — `importlib.resources`
    does not promise that every Traversable's `.name` is a benign basename
    on every backend (filesystem, zip, MetadataPath). Block separators and
    parent-directory references explicitly.
    """
    if not name or name in {".", ".."}:
        return False
    return "/" not in name and "\\" not in name and not name.startswith("..")


def _copy_traversable_entry(src: Traversable, dst: Path) -> None:
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            if not _safe_child_name(child.name):
                _logger.warning(
                    "sdlc init: skipping unsafe package-data name %r under %s",
                    child.name,
                    dst,
                )
                continue
            _copy_traversable_entry(child, dst / child.name)
    else:
        dst.write_bytes(src.read_bytes())


def _copy_package_data_tree(tree_name: str, target_dir: Path) -> None:
    """Copy every file under sdlc/<tree_name>/ from the wheel into target_dir/.

    Uses importlib.resources for zip-safe enumeration. No-op when the tree
    doesn't exist in the wheel (ADR-005 force-include = silent skip on
    missing source).
    """
    try:
        src_root: Traversable = _resource_files("sdlc") / tree_name
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        return
    if not src_root.is_dir():
        return
    for src_entry in src_root.iterdir():
        # Skip .gitkeep placeholder files that exist only for hatch compatibility
        if src_entry.name == ".gitkeep":
            continue
        if not _safe_child_name(src_entry.name):
            _logger.warning(
                "sdlc init: skipping unsafe package-data entry %r under %s",
                src_entry.name,
                tree_name,
            )
            continue
        _copy_traversable_entry(src_entry, target_dir / src_entry.name)


def _create_static_asset_dirs(root: Path) -> None:
    for tree in _STATIC_ASSET_TREES:
        target = root / _CLAUDE_DIR / tree
        target.mkdir(parents=True, exist_ok=True)
        _copy_package_data_tree(tree, target)


def _create_phase_dirs(root: Path) -> None:
    for phase_dir in _PHASE_DIRS:
        (root / phase_dir).mkdir(parents=True, exist_ok=True)


def run_init() -> None:
    """Scaffold the canonical SDLC layout in the current repo.

    Idempotent-via-refusal: if `.claude/state/state.json` already exists,
    prints an error to stderr and exits 1 (no overwrite, no partial write).
    """
    root = _get_repo_root_or_cwd()
    if _state_already_exists(root):
        echo(
            _ALREADY_INITIALIZED_TEMPLATE.format(root=root),
            err=True,
        )
        raise typer.Exit(code=EXIT_USER_ERROR)
    _create_state_subtree(root)
    _create_static_asset_dirs(root)
    _create_phase_dirs(root)
    echo(f"Initialized SDLC framework in {root}")
    echo("  .claude/state/         (state.json, journal.log)")
    echo("  .claude/{agents,commands,hooks,workflows,memory,skills}/")
    echo("  01-Requirement/  02-Architecture/  03-Implementation/")
    echo("Next: sdlc status")

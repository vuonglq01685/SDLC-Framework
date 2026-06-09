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
import sys
import tempfile
from importlib.resources import files as _resource_files

# importlib.resources.abc.Traversable landed in 3.11; fall back to importlib.abc
# for 3.10. The fallback path is only exercised on 3.10; on 3.11+ the primary
# import always succeeds and the deprecated alias under importlib.abc never
# loads (avoids DeprecationWarning that pytest filterwarnings=["error"]
# promotes to a hard error).
try:
    from importlib.resources.abc import Traversable  # see [tool.mypy] importlib override
except ImportError:
    from importlib.abc import Traversable
from pathlib import Path
from typing import Final

import typer

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.exit_codes import EXIT_USER_ERROR
from sdlc.cli.output import echo, emit_error, emit_json

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
        # sdlc: state-write-ok -- Windows os.replace shim for atomic state.json (NTFS).
        os.replace(tmp_path, state_path)  # noqa: state-write -- Windows NTFS atomic initial state.json (Architecture §573; Story 1.20)
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


def _baseline_hook_trust(root: Path) -> None:
    """Delegate to ``sdlc.cli._init_hook_baseline.baseline_hook_trust`` (Story 2A.5 DR4).

    Extracted out of init.py to satisfy the 400-LOC cap per NFR-MAINT-3.
    """
    from sdlc.cli._init_hook_baseline import baseline_hook_trust  # deferred

    baseline_hook_trust(root)


def scaffold_canonical_layout(root: Path) -> None:
    """Create the canonical SDLC directory layout shared by `sdlc init` and `sdlc init --adopt`.

    Creates `.claude/state/` (state.json + journal.log), the static asset trees, and the phase
    dirs — but NOT the hook-trust baseline (callers wrap that separately so they can attach their
    own error envelope). Story 3.1 reuses this instead of reimplementing init scaffolding (AC2).
    """
    _create_state_subtree(root)
    _create_static_asset_dirs(root)
    _create_phase_dirs(root)


def _enumerate_created_paths(root: Path) -> list[str]:
    """Return the relative paths created by `run_init`, sorted (AC4.3).

    Walks the post-init layout and emits every directory and file under the
    canonical SDLC tree (`.claude/state/state.json`, `.claude/state/journal.log`,
    `.claude/{tree}/...` package-data files, `01-Requirement/`, `02-Architecture/`,
    `03-Implementation/`). Paths are POSIX-style so the JSON envelope is stable
    across operating systems.
    """
    created: list[str] = []
    # state subtree files (canonical signal)
    for rel in (".claude/state", ".claude/state/state.json", ".claude/state/journal.log"):
        if (root / rel).exists():
            created.append(rel)
    # static asset trees (.claude/{agents,commands,hooks,workflows,memory,skills}/)
    # plus any files copied from package_data
    for tree in _STATIC_ASSET_TREES:
        tree_root = root / _CLAUDE_DIR / tree
        if tree_root.exists():
            created.append(f"{_CLAUDE_DIR}/{tree}")
            for child in tree_root.rglob("*"):
                rel = child.relative_to(root).as_posix()
                created.append(rel)
    # phase directories
    for phase_dir in _PHASE_DIRS:
        if (root / phase_dir).exists():
            created.append(phase_dir)
    return sorted(set(created))


def run_init(*, ctx: typer.Context | None = None) -> None:
    """Scaffold the canonical SDLC layout in the current repo.

    Idempotent-via-refusal: if `.claude/state/state.json` already exists,
    prints an error to stderr and exits 1 (no overwrite, no partial write).
    """
    root = _get_repo_root_or_cwd()
    if _state_already_exists(root):
        if ctx is not None:
            emit_error(
                "ERR_ALREADY_INITIALIZED",
                f"already initialized at {root}; use `sdlc scan` to refresh state.json",
                ctx=ctx,
                details={"project_root": str(root)},
            )
        echo(
            _ALREADY_INITIALIZED_TEMPLATE.format(root=root),
            err=True,
        )
        raise typer.Exit(code=EXIT_USER_ERROR)
    scaffold_canonical_layout(root)
    try:
        _baseline_hook_trust(root)
    except Exception as exc:
        # DR4: hook-trust baseline failure is fatal for init — surface a
        # typed error envelope so callers see why init aborted.
        if ctx is not None:
            emit_error(
                "ERR_INIT_BASELINE_FAILED",
                f"sdlc init: hook-trust baseline failed: {exc}",
                ctx=ctx,
                details={"project_root": str(root)},
            )
        echo(f"sdlc init: hook-trust baseline failed: {exc}", err=True)
        raise typer.Exit(code=EXIT_USER_ERROR) from exc
    if ctx is not None and ctx.obj is not None and ctx.obj.get("json", False):
        created = _enumerate_created_paths(root)
        emit_json("init", {"project_root": str(root), "created": created}, ctx=ctx)
        return
    echo(f"Initialized SDLC framework in {root}", ctx=ctx)
    echo("  .claude/state/         (state.json, journal.log)", ctx=ctx)
    echo("  .claude/{agents,commands,hooks,workflows,memory,skills}/", ctx=ctx)
    echo("  01-Requirement/  02-Architecture/  03-Implementation/", ctx=ctx)
    echo("Next: sdlc status", ctx=ctx)

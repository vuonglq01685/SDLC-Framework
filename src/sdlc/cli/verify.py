"""`sdlc verify` implementation (Story 2A.10, FR8).

Phase 1 artifact verification ceremony. Wraps the dispatcher's single-specialist
`dispatch(...)` (Story 2A.3) under the Claude PreToolUse bridge (Story 2A.6) +
pre-write hook chain (Story 2A.4); on success appends a `verifications:` list
entry to the artifact's frontmatter and journals `kind=artifact_verified`.

Public surface (D1 single-file stance):

  * D1 chose a "single-file" PUBLIC layout — there is no
    `src/sdlc/verification/` package. Internally, the implementation lives
    across three CLI-private modules to honour the §1052-§1112 LOC cap:

      ┌────────────────────────────────────┬─────────────────────────────┐
      │ module                             │ responsibility              │
      ├────────────────────────────────────┼─────────────────────────────┤
      │ cli/verify.py (this file)          │ Typer entry + pre-flight    │
      │                                    │ + boundary guard + AC3/AC4. │
      │ cli/_verify_frontmatter.py         │ `_Verification` model +     │
      │                                    │ pure parse/append/serialize │
      │                                    │ + canonical body hash.      │
      │ cli/_verify_dispatch.py            │ dispatch wiring + journal   │
      │                                    │ `artifact_verified` emit +  │
      │                                    │ MockAIRuntime fixture.      │
      └────────────────────────────────────┴─────────────────────────────┘

  * `_Verification`, `_parse_frontmatter`, `_append_verification`, and
    `_serialize_artifact` are re-exported from this module so the Task-1
    unit tests (which import them from `sdlc.cli.verify`) continue to
    work without renaming. Helpers MAY be promoted to
    `src/sdlc/verification/` in Story 2A.12 if a non-CLI consumer arises;
    promotion path mirrors Story 2A.7's `SignoffRecord` v1 → v1.x trajectory.

Canonical body hash (AC5 hash-invariance) and the `_Verification` schema
docstrings live in `_verify_frontmatter.py`.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Final

import typer

from sdlc.cli._boundary import artifact_contains_boundary as _artifact_contains_boundary  # P13
from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._verify_dispatch import invoke_dispatch as _invoke_dispatch
from sdlc.cli._verify_frontmatter import (
    _append_verification,
    _parse_frontmatter,
    _serialize_artifact,
    _Verification,
)
from sdlc.cli._verify_paths import (
    _assert_resolved_containment,
    _reject_symlink_ancestors,
)
from sdlc.cli.output import emit_error
from sdlc.errors import StateError

__all__ = (  # noqa: RUF022 — semantic order: model, then helpers in pipeline order
    "_Verification",
    "_parse_frontmatter",
    "_append_verification",
    "_serialize_artifact",
    "run_verify",
)

_STATE_REL: Final[str] = ".claude/state/state.json"
_REQUIREMENT_DIR: Final[str] = "01-Requirement"
_REQUIRED_PHASE: Final[int] = 1
# P3/P4 thresholds (post-review 2026-05-12) — control-char + min-segment guards.
_CONTROL_CHAR_THRESHOLD: Final[int] = 0x20  # everything below 0x20 is C0 control
_DEL_CHAR: Final[int] = 0x7F  # DEL is the lone control char outside the C0 block
_MIN_ARTIFACT_PATH_PARTS: Final[int] = 2  # 01-Requirement/<file>; bare dir refused


# ---------------------------------------------------------------------------
# Pre-flight checks (AC3)
# ---------------------------------------------------------------------------


_MIN_PHASE: Final[int] = 1
_MAX_PHASE: Final[int] = 6


def _read_state_phase(state_path: Path) -> int:
    """Read phase from state.json.

    Best-effort defaults to ``_REQUIRED_PHASE`` on **transient** failures
    (file missing, JSON undecodable) so a recoverable state can still
    surface as ``ERR_NOT_INITIALIZED`` or ``ERR_PHASE_MISMATCH`` downstream.

    P6 / DC4=(1) (post-review 2026-05-12 Cluster C-J): raises
    :class:`sdlc.errors.StateError` on **logical** corruption — the JSON
    decoded fine but the structure is wrong (top-level not a mapping;
    ``phase`` missing, non-int, ``bool``, or out of range 1..6). The caller
    (``_preflight_checks``) translates this into an ``ERR_STATE_CORRUPT``
    envelope that points the operator at ``sdlc rebuild-state``.
    """
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _REQUIRED_PHASE
    if not isinstance(raw, dict):
        raise StateError(
            f"state.json top-level value must be a JSON object; got {type(raw).__name__}"
        )
    phase = raw.get("phase")
    if phase is None:
        raise StateError("state.json missing required 'phase' field")
    # ``bool`` is a subclass of ``int``; reject explicitly so ``"phase": true``
    # never silently coerces to phase=1.
    if isinstance(phase, bool) or not isinstance(phase, int):
        raise StateError(
            f"state.json 'phase' must be an integer in [{_MIN_PHASE}, {_MAX_PHASE}]; "
            f"got {type(phase).__name__}"
        )
    if phase < _MIN_PHASE or phase > _MAX_PHASE:
        raise StateError(
            f"state.json 'phase' out of range [{_MIN_PHASE}, {_MAX_PHASE}]; got {phase}"
        )
    return phase


def _resolve_artifact_path(*, ctx: typer.Context, root: Path, artifact_id: str) -> Path:
    """Resolve `artifact_id` to a repo-relative POSIX path under `01-Requirement/`.

    Rejects absolute paths, `..` traversal, NUL/control-char injection, paths
    that resolve to fewer than 2 segments (i.e. the directory itself), and any
    path that would resolve outside the requirement directory (defends against
    symlink escape).
    """
    # P3 (post-review 2026-05-12): reject NUL bytes + ASCII control characters
    # before they reach `PurePosixPath` / `Path.resolve`. POSIX path semantics
    # forbid NUL bytes; on most OSes `Path(...).resolve()` raises ValueError
    # (uncaught — we only catch OSError below). Explicit early rejection
    # surfaces ERR_PATH_TRAVERSAL with a clear message.
    if not artifact_id or not artifact_id.strip():
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id must be a non-empty repo-relative POSIX path under 01-Requirement/",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )
    if any(ord(ch) < _CONTROL_CHAR_THRESHOLD or ord(ch) == _DEL_CHAR for ch in artifact_id):
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id contains NUL or control characters; refusing to resolve",
            ctx=ctx,
            details={"artifact_id_repr": repr(artifact_id)},
        )

    pure = PurePosixPath(artifact_id)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id must be a repo-relative POSIX path under 01-Requirement/",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )
    if not pure.parts or pure.parts[0] != _REQUIREMENT_DIR:
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id must be a repo-relative POSIX path under 01-Requirement/",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )
    # P4 (post-review 2026-05-12): require at least 2 path segments. Bare
    # `01-Requirement` or `01-Requirement/` would pass parts[0] check but is
    # never a file; reject up-front with a clearer error than the eventual
    # `is_file()` failure downstream.
    if len(pure.parts) < _MIN_ARTIFACT_PATH_PARTS:
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id must include a file segment under 01-Requirement/ "
            "(e.g. 01-Requirement/01-PRODUCT.md)",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )

    candidate = root / Path(*pure.parts)

    # PC2 (post-review 2026-05-12 Cluster C-J): parent-symlink walk extracted
    # to _reject_symlink_ancestors() to keep this orchestrator under the
    # mccabe complexity cap (max=8).
    from sdlc.cli._adopted_targets import load_adopted_target_sources

    adopted_sources = load_adopted_target_sources(root)
    _reject_symlink_ancestors(
        ctx=ctx,
        root=root,
        parts=pure.parts,
        artifact_id=artifact_id,
        adopted_targets=frozenset(adopted_sources),
    )

    try:
        resolved = candidate.resolve(strict=False)
        root_resolved = root.resolve(strict=False)
        target_root = (root_resolved / _REQUIREMENT_DIR).resolve(strict=False)
    except OSError as exc:
        emit_error(
            "ERR_PATH_TRAVERSAL",
            f"could not resolve artifact path: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )

    _assert_resolved_containment(
        ctx=ctx,
        resolved=resolved,
        target_root=target_root,
        root_resolved=root_resolved,
        artifact_id=artifact_id,
        adopted_sources=adopted_sources,
    )

    return candidate


def _preflight_checks(*, ctx: typer.Context, root: Path, artifact_id: str) -> tuple[Path, str]:
    """Run AC3 pre-flight matrix; on success returns (artifact_path, content)."""
    state_path = root / _STATE_REL
    if not state_path.is_file():
        emit_error(
            "ERR_NOT_INITIALIZED",
            f"project not initialized at {root}; run `sdlc init` first",
            ctx=ctx,
            details={"project_root": str(root)},
        )

    try:
        phase = _read_state_phase(state_path)
    except StateError as exc:
        # P6 / DC4=(1): logical corruption — terminal, suggest rebuild-state.
        emit_error(
            "ERR_STATE_CORRUPT",
            f"state.json is corrupt: {exc}; run `sdlc rebuild-state` to recover",
            ctx=ctx,
            details={"state_path": str(state_path)},
        )
    if phase != _REQUIRED_PHASE:
        emit_error(
            "ERR_PHASE_MISMATCH",
            f"sdlc verify requires phase=1; current phase={phase}",
            ctx=ctx,
            details={"phase": phase, "required_phase": _REQUIRED_PHASE},
        )

    artifact_path = _resolve_artifact_path(ctx=ctx, root=root, artifact_id=artifact_id)

    if not artifact_path.is_file():
        emit_error(
            "ERR_ARTIFACT_NOT_FOUND",
            f"artifact not found at {artifact_id}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )

    try:
        content = artifact_path.read_text(encoding="utf-8")
    except PermissionError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"artifact not readable at {artifact_id}: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )
    except UnicodeDecodeError as exc:
        # An adopted leaf symlink can now reach this read (the symlink guard was
        # relaxed for known-adopted targets); a non-UTF-8 source must surface a
        # clean envelope, not an uncaught ValueError traceback.
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"artifact is not valid UTF-8 at {artifact_id}: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )
    except OSError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"artifact read failed at {artifact_id}: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )

    return artifact_path, content


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_verify(*, ctx: typer.Context, artifact_id: str) -> None:
    """Verify a Phase 1 artifact (FR8).

    AC3 pre-flight runs BEFORE any journal append. AC4 boundary guard runs
    BEFORE dispatch is invoked so a polluted artifact never reaches the
    prompt builder. AC5 non-destructive write is enforced by
    `_verify_dispatch.invoke_dispatch` (passing ``persist_artifact=False``
    to the dispatcher). AC7 journals exactly one ``agent_dispatched``
    (from the dispatcher) + one ``artifact_verified`` (from
    `_verify_dispatch`) per successful run.
    """
    root = _get_repo_root_or_cwd()
    artifact_path, artifact_content = _preflight_checks(ctx=ctx, root=root, artifact_id=artifact_id)

    if _artifact_contains_boundary(artifact_content):
        emit_error(
            "ERR_ARTIFACT_CONTAINS_BOUNDARY",
            f"artifact at {artifact_id} contains the data-vs-instruction "
            "boundary marker; refusing to verify — boundary marker is "
            "reserved internal scaffolding",
            ctx=ctx,
            details={"artifact_id": artifact_id},
        )

    _invoke_dispatch(
        ctx=ctx,
        root=root,
        artifact_path=artifact_path,
        artifact_id=artifact_id,
        artifact_content=artifact_content,
    )

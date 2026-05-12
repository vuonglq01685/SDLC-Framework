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

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli._verify_dispatch import invoke_dispatch as _invoke_dispatch
from sdlc.cli._verify_frontmatter import (
    _append_verification,
    _parse_frontmatter,
    _serialize_artifact,
    _Verification,
)
from sdlc.cli.output import emit_error
from sdlc.dispatcher.prompts import BOUNDARY_LINE

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


def _read_state_phase(state_path: Path) -> int:
    """Read phase from state.json (best-effort; returns 1 default on missing field)."""
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _REQUIRED_PHASE
    phase = raw.get("phase") if isinstance(raw, dict) else None
    if isinstance(phase, int):
        return phase
    return _REQUIRED_PHASE


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

    try:
        resolved.relative_to(target_root)
    except ValueError:
        emit_error(
            "ERR_PATH_TRAVERSAL",
            "artifact_id resolves outside 01-Requirement/ (symlink escape or directory traversal)",
            ctx=ctx,
            details={
                "artifact_id": artifact_id,
                "resolved": str(resolved),
            },
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

    phase = _read_state_phase(state_path)
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
    except OSError as exc:
        emit_error(
            "ERR_ARTIFACT_UNREADABLE",
            f"artifact read failed at {artifact_id}: {exc}",
            ctx=ctx,
            details={"artifact_id": artifact_id, "path": str(artifact_path)},
        )

    return artifact_path, content


# ---------------------------------------------------------------------------
# Boundary-marker artifact guard (AC4)
# ---------------------------------------------------------------------------


def _artifact_contains_boundary(content: str) -> bool:
    """Return True iff `content` contains the canonical BOUNDARY_LINE.

    Bytewise substring match; NOT Markdown-aware. Even content inside fenced
    code blocks triggers rejection. The check defends against the homograph
    attack where a Phase-1 artifact embeds the data-vs-instruction marker
    in its body — without the guard, the verifier prompt (which embeds the
    artifact as `idea_text`) could be tricked into following an in-band
    `</USER_IDEA>` block followed by adversarial instructions.
    """
    return BOUNDARY_LINE in content


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

"""`sdlc verify` implementation (Story 2A.10, FR8).

Phase 1 artifact verification ceremony. Wraps the dispatcher's single-specialist
`dispatch(...)` (Story 2A.3) under the Claude PreToolUse bridge (Story 2A.6) +
pre-write hook chain (Story 2A.4); on success appends a `verifications:` list
entry to the artifact's frontmatter and journals `kind=artifact_verified`.

Layout follows AC8/D1 (single-file): the `_Verification` model + the three
pure frontmatter helpers (`_parse_frontmatter`, `_append_verification`,
`_serialize_artifact`) live in this module. Helpers MAY be promoted to
`src/sdlc/verification/` in Story 2A.12 if a non-CLI consumer arises;
promotion path mirrors Story 2A.7's `SignoffRecord` v1 → v1.x trajectory.

Canonical body hash: `content_hash_at_verify` hashes the body bytes AFTER the
second `---` delimiter (with trailing newline canonicalisation). The hash is
deliberately invariant under frontmatter-only edits (subsequent verifications,
signoff record updates) — distinct from Story 2A.7's `compute_artifact_hash`
which hashes ON-DISK BYTES VERBATIM. Both hashes serve different audit
purposes; do NOT conflate.

The `_Verification` model is a private internal contract; `extra="forbid"`
+ `frozen=True` are inherited from `StrictModel` (ADR-025). Promotion to
a frozen wire-format snapshot is deferred per AC6/D2.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Final, Literal

import typer
import yaml
from pydantic import StringConstraints, ValidationError

from sdlc.cli._paths import get_repo_root_or_cwd as _get_repo_root_or_cwd
from sdlc.cli.output import emit_error
from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import WorkflowError

__all__ = (  # noqa: RUF022 — semantic order: model, then helpers in pipeline order (parse → append → serialize)
    "_Verification",
    "_parse_frontmatter",
    "_append_verification",
    "_serialize_artifact",
    "run_verify",
)

_FRONTMATTER_DELIMITER = "---"
_TS_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"

_STATE_REL: Final[str] = ".claude/state/state.json"
_JOURNAL_REL: Final[str] = ".claude/state/journal.log"
_REQUIREMENT_DIR: Final[str] = "01-Requirement"
_REQUIRED_PHASE: Final[int] = 1


class _Verification(StrictModel):
    """Single verification entry in an artifact's frontmatter.

    NOT exported from `sdlc.contracts`. NOT a frozen wire-format contract;
    on-disk YAML schema may evolve in v1.x without ADR-024 ceremony
    (promotion deferred per AC6/D2). Story 2A.12 (`/sdlc-signoff`) is the
    expected first non-CLI consumer; promote then if needed.
    """

    schema_version: Literal[1] = 1
    verifier: str
    ts: Annotated[str, StringConstraints(pattern=_TS_PATTERN)]
    status: Literal["verified", "failed", "advisory"] = "verified"
    content_hash_at_verify: Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
    verifier_note: Annotated[str, StringConstraints(max_length=500)] | None = None


def _split_frontmatter_block(content: str) -> tuple[str, str] | None:
    """Return `(yaml_block, body)` if `content` opens with a `---` block; else None."""
    if not content.startswith(_FRONTMATTER_DELIMITER + "\n") and content != _FRONTMATTER_DELIMITER:
        return None
    lines = content.split("\n")
    if not lines or lines[0] != _FRONTMATTER_DELIMITER:
        return None
    for idx in range(1, len(lines)):
        if lines[idx] == _FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:idx]), "\n".join(lines[idx + 1 :])
    return None


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split `content` into `(frontmatter_dict, body)`.

    Returns `({}, content)` if no frontmatter delimiter is found at the top.
    Frontmatter is the YAML block between the first two `---` lines. The
    parser is hand-rolled (no `python-frontmatter` dependency); see
    `cli/scan.py` for the analogous split-on-delimiter pattern.

    Raises `WorkflowError` if the YAML fails to parse OR if the parsed
    structure is not a mapping (we never accept top-level lists / scalars
    in artifact frontmatter).
    """
    split = _split_frontmatter_block(content)
    if split is None:
        return {}, content

    yaml_block, body = split
    try:
        parsed = yaml.safe_load(yaml_block) if yaml_block.strip() else {}
    except yaml.YAMLError as exc:
        raise WorkflowError(f"frontmatter YAML parse failed: {exc}") from exc

    if parsed is None:
        parsed = {}

    if not isinstance(parsed, dict):
        raise WorkflowError(f"frontmatter must be a YAML mapping; got {type(parsed).__name__}")

    return parsed, body


def _append_verification(frontmatter: dict[str, Any], entry: _Verification) -> dict[str, Any]:
    """Return a NEW frontmatter dict with `entry` appended to `verifications:`.

    Does NOT mutate `frontmatter`. Initialises `verifications: []` when the
    field is absent or `None`. Existing entries are preserved bit-exact via
    `copy.deepcopy`.
    """
    new_fm = copy.deepcopy(frontmatter)
    existing = new_fm.get("verifications")
    if existing is None:
        existing_list: list[dict[str, Any]] = []
    elif isinstance(existing, list):
        existing_list = list(existing)
    else:
        raise WorkflowError(f"verifications: must be a list or null; got {type(existing).__name__}")

    existing_list.append(entry.model_dump(mode="python"))
    new_fm["verifications"] = existing_list
    return new_fm


def _serialize_artifact(frontmatter: dict[str, Any], body: str) -> str:
    """Re-serialise `frontmatter` + `body` into canonical artifact bytes.

    Empty frontmatter → returns `body` unchanged (no `---` delimiters).
    Non-empty → emits `---\\n<yaml>---\\n<body>` with `yaml.safe_dump`
    configured for sorted keys, block style, allow_unicode. Always ensures
    a trailing newline.
    """
    if not frontmatter:
        if body and not body.endswith("\n"):
            return body + "\n"
        return body

    yaml_block = yaml.safe_dump(
        frontmatter,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )

    serialized = f"{_FRONTMATTER_DELIMITER}\n{yaml_block}{_FRONTMATTER_DELIMITER}\n{body}"
    if not serialized.endswith("\n"):
        serialized = serialized + "\n"
    return serialized


_VALIDATION_ERROR_TYPES: tuple[type[Exception], ...] = (ValidationError,)


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

    Rejects absolute paths, `..` traversal, and any path that would resolve
    outside the requirement directory (defends against symlink escape).
    """
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
# Dispatch entry point (Task 5 will fill this in)
# ---------------------------------------------------------------------------


def _invoke_dispatch(
    *,
    ctx: typer.Context,
    root: Path,
    artifact_path: Path,
    artifact_id: str,
    artifact_content: str,
) -> None:
    """Dispatch the artifact-verifier specialist + append verification entry.

    NOTE: stub for Task 2; the full wiring lands in Task 5 (commit 5)
    once `workflows_yaml/sdlc-verify.yaml` + the specialist stub exist.
    """
    raise NotImplementedError("sdlc verify dispatch wiring lands in Story 2A.10 Task 5")


def run_verify(*, ctx: typer.Context, artifact_id: str) -> None:
    """Verify a Phase 1 artifact (FR8).

    AC3 pre-flight is performed BEFORE any journal append; AC4 boundary
    guard runs in Task 3; full dispatch + frontmatter append lands in Task 5.
    """
    root = _get_repo_root_or_cwd()
    artifact_path, artifact_content = _preflight_checks(ctx=ctx, root=root, artifact_id=artifact_id)

    _invoke_dispatch(
        ctx=ctx,
        root=root,
        artifact_path=artifact_path,
        artifact_id=artifact_id,
        artifact_content=artifact_content,
    )

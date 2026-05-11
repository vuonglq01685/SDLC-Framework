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
from typing import Annotated, Any, Literal

import yaml
from pydantic import StringConstraints, ValidationError

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import WorkflowError

__all__ = (  # noqa: RUF022 — semantic order: model, then helpers in pipeline order (parse → append → serialize)
    "_Verification",
    "_parse_frontmatter",
    "_append_verification",
    "_serialize_artifact",
)

_FRONTMATTER_DELIMITER = "---"
_TS_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


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

"""Frontmatter primitives for `sdlc verify` (Story 2A.10, FR8).

Private CLI-internal module. The `_Verification` model + the three pure
helpers (`_parse_frontmatter`, `_append_verification`, `_serialize_artifact`)
+ the canonical body-hash helpers live here so `cli/verify.py` stays under
the §1052-§1112 LOC cap. D1 chose a "single-file" PUBLIC layout (no
`src/sdlc/verification/` package); splitting INTERNALLY into a
private-prefixed sibling honours that spirit — the public surface is
re-exported from `cli/verify` for backwards compatibility with the
Task-1 unit tests.

Canonical body hash (AC5 hash-invariance):

  * `content_hash_at_verify` hashes the body bytes AFTER the second `---`
    delimiter, canonicalised under a single-trailing-newline rule that
    matches `_serialize_artifact`. The hash is deliberately invariant
    under frontmatter-only edits (subsequent verifications, signoff
    record updates).
  * Compare against Story 2A.7's `compute_artifact_hash` which hashes
    ON-DISK BYTES VERBATIM. Both hashes serve different audit purposes;
    do NOT conflate.

The `_Verification` model is a private internal contract; `extra="forbid"`
+ `frozen=True` are inherited from `StrictModel` (ADR-025). Promotion to
a frozen wire-format snapshot is deferred per AC6/D2.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Annotated, Any, Final, Literal

import yaml
from pydantic import StringConstraints

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import WorkflowError

__all__ = (  # noqa: RUF022 — semantic order: model first, helpers in pipeline order
    "_Verification",
    "_parse_frontmatter",
    "_append_verification",
    "_serialize_artifact",
    "_canonical_body",
    "_compute_body_hash",
    "FRONTMATTER_DELIMITER",
    "VERIFIER_NOTE_MAX_LEN",
    "ALLOWED_STATUSES",
)

FRONTMATTER_DELIMITER: Final[str] = "---"
_TS_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
VERIFIER_NOTE_MAX_LEN: Final[int] = 500
ALLOWED_STATUSES: Final[frozenset[str]] = frozenset({"verified", "failed", "advisory"})


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
    verifier_note: Annotated[str, StringConstraints(max_length=VERIFIER_NOTE_MAX_LEN)] | None = None


_BOM: Final[str] = "﻿"


def _normalize_line_endings(content: str) -> str:
    """P5 / DC3=(a) (post-review 2026-05-12 Cluster C-J): strip UTF-8 BOM and
    normalise CRLF/CR line endings to LF before frontmatter detection.

    Without this, a Markdown artifact saved by a Windows editor (CRLF) or
    served with a BOM silently fails the ``startswith("---\\n")`` check in
    :func:`_split_frontmatter_block` and is treated as having NO frontmatter
    — the verify ceremony then appends a fresh ``verifications:`` block on
    top of the (CRLF) body, and downstream re-reads observe a body hash
    that depends on the file's line-ending convention. Normalising up-front
    makes the body-hash invariant under {LF, CRLF, BOM+LF, BOM+CRLF}
    representations of identical text.
    """
    if content.startswith(_BOM):
        content = content[len(_BOM) :]
    # Normalise CRLF → LF first to avoid creating empty lines from bare CR.
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _split_frontmatter_block(content: str) -> tuple[str, str] | None:
    """Return `(yaml_block, body)` if `content` opens with a `---` block; else None.

    Input is assumed to already be BOM-stripped + line-ending-normalised
    via :func:`_normalize_line_endings`; :func:`_parse_frontmatter` applies
    the normalisation up-front so EVERY call path (including the
    no-frontmatter return) sees a canonical representation. PC5/DC3=a.
    """
    if not content.startswith(FRONTMATTER_DELIMITER + "\n") and content != FRONTMATTER_DELIMITER:
        return None
    lines = content.split("\n")
    if not lines or lines[0] != FRONTMATTER_DELIMITER:
        return None
    for idx in range(1, len(lines)):
        if lines[idx] == FRONTMATTER_DELIMITER:
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
    # P5 / DC3=(a): normalise BOM + CRLF up-front so the body returned to
    # callers (including the no-frontmatter return below) is canonical. This
    # makes :func:`_compute_body_hash` invariant under {LF, CRLF, BOM} edits
    # of the SAME LOGICAL CONTENT — drives 2A.12 drift detection per AC7.
    content = _normalize_line_endings(content)

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

    serialized = f"{FRONTMATTER_DELIMITER}\n{yaml_block}{FRONTMATTER_DELIMITER}\n{body}"
    if not serialized.endswith("\n"):
        serialized = serialized + "\n"
    return serialized


def _canonical_body(body: str) -> str:
    """Return ``body`` with a single trailing newline (matches `_serialize_artifact`).

    Empty body stays empty. Non-empty body is given exactly one trailing
    ``\\n``. This must agree with ``_serialize_artifact`` so a parse →
    serialize → parse round-trip yields hash-stable bytes (re-verification
    of an unedited artifact MUST reproduce the same `content_hash_at_verify`).
    """
    if not body:
        return body
    if body.endswith("\n"):
        return body
    return body + "\n"


def _compute_body_hash(content: str) -> str:
    """Hash the body bytes AFTER the second `---` delimiter (canonicalised).

    Frontmatter bytes are deliberately excluded so a subsequent
    frontmatter-only edit (e.g. appending another `verifications:` entry)
    does NOT mutate the hash. See module docstring for the comparison
    against Story 2A.7's `compute_artifact_hash`.
    """
    _, body = _parse_frontmatter(content)
    canonical = _canonical_body(body)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

"""Defensive-branch coverage for `_verify_frontmatter` helpers (Story 2A.10).

Extends `test_verify_frontmatter.py` with explicit coverage of the rare
parse/serialize edge cases the e2e + integration suites do not exercise.
"""

from __future__ import annotations

import pytest

from sdlc.cli._verify_frontmatter import (
    _append_verification,
    _canonical_body,
    _parse_frontmatter,
    _serialize_artifact,
    _split_frontmatter_block,
    _Verification,
)
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit


_VALID_TS = "2026-05-11T12:34:56.789Z"
_VALID_HASH = "sha256:" + "a" * 64


def _entry() -> _Verification:
    return _Verification(
        verifier="artifact-verifier",
        ts=_VALID_TS,
        content_hash_at_verify=_VALID_HASH,
    )


# ---------------------------------------------------------------------------
# _split_frontmatter_block defensive returns
# ---------------------------------------------------------------------------


def test_split_returns_none_when_no_closing_delimiter() -> None:
    """An opening `---` with no matching close is not frontmatter."""
    content = "---\nfoo: bar\nbaz: qux\nno close here\n"
    assert _split_frontmatter_block(content) is None


def test_split_returns_none_when_no_opening_delimiter() -> None:
    """Plain markdown body returns None."""
    assert _split_frontmatter_block("# heading\n\nbody text\n") is None


def test_split_handles_bare_delimiter_line_only() -> None:
    """A `---` that is the entire file returns None (no body, no close)."""
    assert _split_frontmatter_block("---") is None


# ---------------------------------------------------------------------------
# _parse_frontmatter: None YAML + non-mapping YAML
# ---------------------------------------------------------------------------


def test_parse_frontmatter_empty_yaml_block_returns_empty_dict() -> None:
    """An opened frontmatter block with no keys parses as `{}`."""
    content = "---\n---\nbody here\n"
    fm, body = _parse_frontmatter(content)
    assert fm == {}
    assert body == "body here\n"


def test_parse_frontmatter_yaml_null_normalised_to_empty_dict() -> None:
    """Yaml `null` / a single `~` (which `safe_load` decodes as None) → {}."""
    content = "---\n~\n---\nbody\n"
    fm, _body = _parse_frontmatter(content)
    assert fm == {}


def test_parse_frontmatter_list_top_level_raises() -> None:
    """A YAML list at the top of frontmatter is rejected."""
    content = "---\n- a\n- b\n---\nbody\n"
    with pytest.raises(WorkflowError, match="must be a YAML mapping"):
        _parse_frontmatter(content)


def test_parse_frontmatter_malformed_yaml_raises_workflow_error() -> None:
    """Unparseable YAML inside the block surfaces as `WorkflowError`."""
    content = "---\nkey: : badly: nested:\n  - mixed: : tokens\n---\nbody\n"
    with pytest.raises(WorkflowError, match="parse failed"):
        _parse_frontmatter(content)


# ---------------------------------------------------------------------------
# _append_verification: invalid existing `verifications:` shape
# ---------------------------------------------------------------------------


def test_append_verification_rejects_non_list_verifications_field() -> None:
    """If `verifications:` already holds a scalar, the helper refuses."""
    bad_fm: dict[str, object] = {"verifications": "not-a-list"}
    with pytest.raises(WorkflowError, match="must be a list or null"):
        _append_verification(bad_fm, _entry())


def test_append_verification_treats_null_existing_as_empty() -> None:
    """`verifications: null` is normalised to `[]` before appending."""
    fm: dict[str, object] = {"verifications": None}
    new_fm = _append_verification(fm, _entry())
    rows = new_fm["verifications"]
    assert isinstance(rows, list)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# _serialize_artifact + _canonical_body: trailing-newline normalisation
# ---------------------------------------------------------------------------


def test_serialize_empty_frontmatter_appends_newline_to_body() -> None:
    """When frontmatter is empty and body lacks a trailing newline, one is added."""
    out = _serialize_artifact({}, "no trailing newline")
    assert out == "no trailing newline\n"


def test_serialize_empty_frontmatter_preserves_body_with_newline() -> None:
    """Body already ending in `\\n` is returned unchanged."""
    out = _serialize_artifact({}, "already terminated\n")
    assert out == "already terminated\n"


def test_canonical_body_empty_string_returned_as_is() -> None:
    """`_canonical_body("")` returns the empty string (no newline injected)."""
    assert _canonical_body("") == ""


def test_canonical_body_already_terminated_passes_through() -> None:
    """Body that already ends with `\\n` is returned bit-exact."""
    assert _canonical_body("body\n") == "body\n"


def test_canonical_body_missing_newline_gets_one_appended() -> None:
    """Body without a trailing `\\n` is given exactly one."""
    assert _canonical_body("body") == "body\n"


# ---------------------------------------------------------------------------
# P24 / DC12=(a) (post-review 2026-05-12 Cluster C-J)
# Body-hash invariance across no-frontmatter -> with-frontmatter transition.
# The first verify appends a `verifications:` block; body bytes are
# unchanged. The canonical body hash MUST be invariant — drives 2A.12
# drift detection per DC8 + AC7.
# ---------------------------------------------------------------------------


def test_body_hash_invariant_across_no_fm_to_with_fm_transition() -> None:
    """no-fm -> with-fm (1 entry) -> with-fm (2 entries) — body hash stable."""
    from sdlc.cli._verify_frontmatter import _compute_body_hash

    body = "# Heading\n\nSome content.\n"
    state_1 = body
    h1 = _compute_body_hash(state_1)

    state_2 = _serialize_artifact({"verifications": [_entry().model_dump(mode="python")]}, body)
    h2 = _compute_body_hash(state_2)

    state_3 = _serialize_artifact(
        {"verifications": [_entry().model_dump(mode="python"), _entry().model_dump(mode="python")]},
        body,
    )
    h3 = _compute_body_hash(state_3)

    assert h1 == h2 == h3, (
        f"body-hash must be invariant across no-fm -> with-fm transition; got {h1=}, {h2=}, {h3=}"
    )


def test_body_hash_invariant_under_crlf_line_endings() -> None:
    """P5 / DC3=(a): CRLF and LF representations of the same body yield
    identical hashes after BOM/CRLF normalisation in
    `_split_frontmatter_block`.
    """
    from sdlc.cli._verify_frontmatter import _compute_body_hash

    body_lf = "# Heading\n\nLine one.\nLine two.\n"
    body_crlf = body_lf.replace("\n", "\r\n")
    assert _compute_body_hash(body_lf) == _compute_body_hash(body_crlf)


def test_body_hash_invariant_under_bom_prefix() -> None:
    """P5 / DC3=(a): UTF-8 BOM prefix is stripped before hashing."""
    from sdlc.cli._verify_frontmatter import _compute_body_hash

    body = "# Heading\n\nBody.\n"
    body_with_bom = "﻿" + body
    assert _compute_body_hash(body) == _compute_body_hash(body_with_bom)

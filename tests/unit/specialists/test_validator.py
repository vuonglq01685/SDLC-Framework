"""Tests for specialists/_validator.py — validate_workflow_refs + validate_internal_links."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import SpecialistError
from sdlc.specialists import (
    SpecialistRegistry,
    load_registry,
    validate_internal_links,
    validate_workflow_refs,
)
from sdlc.specialists._validator import _LINK_RE, _WIKILINK_RE

_VALIDATOR_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "validator"
_WF_REFS = _VALIDATOR_FIXTURES / "workflow_refs"
_LINKS = _VALIDATOR_FIXTURES / "internal_links"
_VALID_AGENTS = (
    Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "registry" / "valid_agents"
)


def _load_spec(filename: str) -> WorkflowSpec:
    data = yaml.safe_load((_WF_REFS / filename).read_text())
    return WorkflowSpec.model_validate(data)


def _make_registry() -> SpecialistRegistry:
    return load_registry(_VALID_AGENTS)


# ---------------------------------------------------------------------------
# validate_workflow_refs — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_workflow_refs_valid_does_not_raise() -> None:
    spec = _load_spec("valid.yaml")
    reg = _make_registry()
    validate_workflow_refs(spec, reg)  # must not raise


# ---------------------------------------------------------------------------
# validate_workflow_refs — violations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_workflow_refs_missing_primary_raises() -> None:
    spec = _load_spec("missing_primary.yaml")
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    violations = str(exc_info.value.details.get("violations", []))
    assert "primary_agent" in violations


@pytest.mark.unit
def test_validate_workflow_refs_missing_parallel_raises() -> None:
    spec = _load_spec("missing_parallel.yaml")
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    violations = str(exc_info.value.details.get("violations", []))
    assert "parallel_agents" in violations


@pytest.mark.unit
def test_validate_workflow_refs_missing_synthesizer_raises() -> None:
    spec = _load_spec("missing_synthesizer.yaml")
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    violations = str(exc_info.value.details.get("violations", []))
    assert "synthesizer_agent" in violations


@pytest.mark.unit
def test_validate_workflow_refs_globs_drift_raises() -> None:
    spec = _load_spec("globs_drift.yaml")
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    violations = str(exc_info.value.details.get("violations", []))
    assert "write_globs" in violations


@pytest.mark.unit
def test_validate_workflow_refs_multi_violation_fail_once_with_full_list() -> None:
    """All violations collected and surfaced in a single SpecialistError."""
    spec = _load_spec("multi_violation.yaml")
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    err = exc_info.value
    # Must include violations list in details (fail-once-with-full-list pattern).
    assert "violations" in err.details
    assert isinstance(err.details["violations"], list)
    assert len(err.details["violations"]) >= 2  # multiple violations


# ---------------------------------------------------------------------------
# validate_internal_links — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_internal_links_empty_bodies_does_not_raise() -> None:
    """Registry where specialist bodies have NO links must not raise (degenerate happy path)."""
    reg = _make_registry()
    # valid_agents specialists have no body links — degenerate case.
    validate_internal_links(reg)


@pytest.mark.unit
def test_validate_internal_links_resolves_valid_refs() -> None:
    """Registry whose bodies cross-reference real specialists must not raise (P-R8).

    Stronger than the empty-bodies test: this exercises the regex/match path
    on real names that ARE in the registry, pinning the validator's loop body
    against tautological regressions (e.g. a future bug where the loop never
    runs would pass the empty-bodies test but fail this one).
    """
    from sdlc.specialists._frontmatter import Specialist

    base_reg = _make_registry()
    alpha = base_reg.get("alpha-researcher")
    cross_ref_alpha = Specialist(
        frontmatter=alpha.frontmatter,
        body="See [Beta](agents/beta-analyst.md) and [[gamma-support]] for details.",
        source_path=alpha.source_path,
        phase=alpha.phase,
    )
    overlay = {
        "alpha-researcher": cross_ref_alpha,
        "beta-analyst": base_reg.get("beta-analyst"),
        "gamma-support": base_reg.get("gamma-support"),
    }
    reg = SpecialistRegistry(_specialists=__import__("types").MappingProxyType(overlay))
    validate_internal_links(reg)  # must not raise — alpha's body refs resolve


# ---------------------------------------------------------------------------
# validate_internal_links — violations (using inline Specialist construction)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_internal_links_dangling_link_raises() -> None:
    from sdlc.specialists._frontmatter import load_specialist

    dangling = load_specialist(_LINKS / "dangling-link.md")
    reg = SpecialistRegistry(
        _specialists=__import__("types").MappingProxyType({"dangling-link": dangling})
    )
    with pytest.raises(SpecialistError, match="dangling"):
        validate_internal_links(reg)


@pytest.mark.unit
def test_validate_internal_links_dangling_wikilink_raises() -> None:

    from sdlc.specialists._frontmatter import load_specialist

    dangling = load_specialist(_LINKS / "dangling-wikilink.md")
    reg = SpecialistRegistry(
        _specialists=__import__("types").MappingProxyType({"dangling-wikilink": dangling})
    )
    with pytest.raises(SpecialistError, match="dangling"):
        validate_internal_links(reg)


# ---------------------------------------------------------------------------
# _LINK_RE / _WIKILINK_RE exported constants (AC6)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_link_re_matches_agent_link() -> None:
    body = "See [Alpha](agents/alpha-researcher.md) for details."
    m = _LINK_RE.search(body)
    assert m is not None
    assert m.group("name") == "alpha-researcher"


@pytest.mark.unit
def test_link_re_matches_agent_link_with_anchor() -> None:
    body = "See [Alpha](agents/alpha-researcher.md#section) for details."
    m = _LINK_RE.search(body)
    assert m is not None
    assert m.group("name") == "alpha-researcher"


@pytest.mark.unit
def test_wikilink_re_matches_wikilink() -> None:
    body = "See [[beta-analyst]] for more."
    m = _WIKILINK_RE.search(body)
    assert m is not None
    assert m.group("name") == "beta-analyst"


@pytest.mark.unit
def test_link_re_does_not_match_non_agent_links() -> None:
    body = "See [External](https://example.com) for info."
    assert _LINK_RE.search(body) is None


# ---------------------------------------------------------------------------
# P-R4: validate_internal_links must skip fenced code blocks, HTML comments,
# and inline code spans. Documentation snippets with dangling refs must not
# surface as false-positive orphan errors.
# ---------------------------------------------------------------------------


def _single_specialist_registry(fixture_filename: str) -> SpecialistRegistry:
    """Build a one-specialist registry from a fixture file (test helper)."""
    from sdlc.specialists._frontmatter import load_specialist

    s = load_specialist(_LINKS / fixture_filename)
    return SpecialistRegistry(
        _specialists=__import__("types").MappingProxyType({s.frontmatter.name: s})
    )


@pytest.mark.unit
def test_validate_internal_links_skips_fenced_code_block() -> None:
    reg = _single_specialist_registry("dangling-in-code-block.md")
    validate_internal_links(reg)  # must not raise


@pytest.mark.unit
def test_validate_internal_links_skips_html_comment() -> None:
    reg = _single_specialist_registry("dangling-in-html-comment.md")
    validate_internal_links(reg)


@pytest.mark.unit
def test_validate_internal_links_skips_inline_code_span() -> None:
    reg = _single_specialist_registry("dangling-in-inline-code.md")
    validate_internal_links(reg)


# ---------------------------------------------------------------------------
# P-R23 (D-R3 option b): unsupported link forms are intentional no-ops.
# Documents the AC6 scope decision via a runtime test.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_internal_links_unsupported_forms_are_noops() -> None:
    """./agents/, ../agents/, link-with-title, padded wikilinks — all out of AC6 scope."""
    reg = _single_specialist_registry("unsupported-forms.md")
    validate_internal_links(reg)


# ---------------------------------------------------------------------------
# P-R24 (D-R4 option a): self-reference is intentionally allowed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_internal_links_self_reference_allowed() -> None:
    reg = _single_specialist_registry("self-reference.md")
    validate_internal_links(reg)  # self-link must not raise


# ---------------------------------------------------------------------------
# P-R6: violations are deduplicated; len(unique) reflects unique offending
# refs, not call counts.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validate_workflow_refs_dedupes_repeated_violations() -> None:
    """parallel_agents=['x','x'] for unknown 'x' should report once."""
    spec = WorkflowSpec.model_validate(
        {
            "schema_version": 1,
            "name": "dup-test-workflow",
            "slash_command": "/dup-test",
            "primary_agent": "alpha-researcher",
            "parallel_agents": ["unknown-x", "unknown-x"],
            "synthesizer_agent": None,
            "postconditions": [],
            "write_globs": {},
            "stop_on_postcondition_failure": True,
        }
    )
    reg = _make_registry()
    with pytest.raises(SpecialistError) as exc_info:
        validate_workflow_refs(spec, reg)
    violations = exc_info.value.details["violations"]
    assert isinstance(violations, list)
    assert len(violations) == len(set(violations))  # all unique
    assert sum(1 for v in violations if "unknown-x" in v) == 1

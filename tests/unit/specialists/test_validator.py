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
def test_validate_internal_links_valid_does_not_raise() -> None:
    """Registry where specialist body has valid links — must not raise."""
    reg = _make_registry()
    # valid_agents specialists have no body links — must not raise.
    validate_internal_links(reg)


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

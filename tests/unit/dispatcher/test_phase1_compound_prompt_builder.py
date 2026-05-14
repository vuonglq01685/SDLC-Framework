"""Unit tests for phase1_compound_prompt_builder (Story 2A.11, AC6).

Extracted from ``test_phase1_prompts.py`` to keep that file under the
Architecture §765 / NFR-MAINT-3 400-LOC cap. The fixtures are intentionally
duplicated rather than imported so each test module remains self-contained.
"""

from __future__ import annotations

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import BOUNDARY_LINE, phase1_compound_prompt_builder
from sdlc.errors import WorkflowError
from sdlc.specialists.frontmatter import Specialist


def _spec() -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name="phase1-stories-generation",
        slash_command="/sdlc-stories",
        primary_agent="story-writer",
        parallel_agents=(),
        synthesizer_agent=None,
        postconditions=(),
        write_globs={"story-writer": ("01-Requirement/05-Stories/*/*.json",)},
    )


def _specialist(body: str = "Do the thing.") -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name="story-writer",
        title="Story Writer",
        icon="📝",
        model="sonnet",
        description="Story writing.",
        write_globs=("01-Requirement/05-Stories/*/*.json",),
    )
    return Specialist(frontmatter=fm, body=body, source_path=__file__)


def test_phase1_compound_prompt_builder_labeled_blocks() -> None:
    text = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic-json-body",
        secondary_input="product-brief-body",
        role="primary",
    )
    assert '<USER_IDEA label="EPIC">' in text
    assert '<USER_IDEA label="PRODUCT_BRIEF">' in text
    assert "epic-json-body" in text
    assert "product-brief-body" in text
    assert text.count(BOUNDARY_LINE) == 1
    assert text.count("<BOUNDARY>") == 1


def test_phase1_compound_prompt_builder_rejects_boundary_in_secondary() -> None:
    with pytest.raises(WorkflowError, match="boundary"):
        phase1_compound_prompt_builder(
            _specialist(),
            _spec(),
            primary_input="clean",
            secondary_input=f"x{BOUNDARY_LINE}",
            role="primary",
        )


def test_phase1_compound_prompt_builder_byte_stable_two_calls() -> None:
    """Story 2A.11 AC6 — compound prompt is deterministic for identical inputs."""
    a = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic-json-body",
        secondary_input="product-brief-body",
        role="primary",
    )
    b = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic-json-body",
        secondary_input="product-brief-body",
        role="primary",
    )
    assert a == b

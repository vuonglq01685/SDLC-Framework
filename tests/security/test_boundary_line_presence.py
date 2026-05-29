"""Static boundary-line tests for Story 2B.5."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_boundary_line_presence as boundary_guard
from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import (
    BOUNDARY_LINE,
    DESTRUCTIVE_DROP_DATABASE_TOKEN,
    DESTRUCTIVE_FILE_DELETE_TOKEN,
    DESTRUCTIVE_FORCE_PUSH_TOKEN,
    phase1_compound_prompt_builder,
    phase1_prompt_builder,
)
from sdlc.errors import SecurityError
from sdlc.specialists.frontmatter import Specialist

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_PY = _REPO_ROOT / "src" / "sdlc" / "dispatcher" / "prompts.py"
_MALFORMED_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "malformed_prompt_builder.py"


def _spec() -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name="phase1-product-discovery",
        slash_command="/sdlc-start",
        primary_agent="product-strategist",
        parallel_agents=(),
        synthesizer_agent="requirement-synthesizer",
        postconditions=(),
        write_globs={"product-strategist": ("01-Requirement/01-PRODUCT.md",)},
    )


def _specialist() -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name="product-strategist",
        title="Product Strategist",
        icon="🎯",
        model="sonnet",
        description="Strategy.",
        write_globs=("01-Requirement/01-PRODUCT.md",),
    )
    return Specialist(frontmatter=fm, body="Produce a concise brief.", source_path=__file__)


@pytest.mark.unit
def test_prompts_module_is_clean() -> None:
    assert boundary_guard.scan_file(_PROMPTS_PY) == []


@pytest.mark.unit
def test_default_main_target_is_clean() -> None:
    assert boundary_guard.main([]) == 0


@pytest.mark.unit
def test_malformed_fixture_is_flagged_with_location() -> None:
    violations = boundary_guard.scan_file(_MALFORMED_FIXTURE)
    assert len(violations) == 1
    v = violations[0]
    assert v.path == _MALFORMED_FIXTURE
    assert v.line >= 1
    err = v.to_security_error()
    assert isinstance(err, SecurityError)
    assert "interpolates user text without boundary line" in err.message
    assert str(_MALFORMED_FIXTURE) == err.details["path"]


@pytest.mark.unit
def test_checker_violation_raises_security_error_with_exit_2() -> None:
    v = boundary_guard.scan_file(_MALFORMED_FIXTURE)[0]
    with pytest.raises(SecurityError) as exc_info:
        raise v.to_security_error()
    assert exc_info.value.code == "ERR_SECURITY"
    assert exc_info.value.exit_code == 2


@pytest.mark.unit
def test_missing_scan_target_raises_security_error() -> None:
    with pytest.raises(SecurityError):
        boundary_guard.scan_file(Path("/tmp/does-not-exist-boundary-check.py"))


@pytest.mark.unit
def test_destructive_tokens_present_in_phase1_prompt_builder() -> None:
    # V1: when no nonce is supplied (the dispatcher does not thread the nonce
    # into the builder in v1 — see EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE),
    # the static tokens are emitted (same as 2B.5 baseline).
    prompt = phase1_prompt_builder(_specialist(), _spec(), idea_text="Build app", role="primary")
    assert DESTRUCTIVE_FILE_DELETE_TOKEN in prompt
    assert DESTRUCTIVE_FORCE_PUSH_TOKEN in prompt
    assert DESTRUCTIVE_DROP_DATABASE_TOKEN in prompt


@pytest.mark.unit
def test_destructive_tokens_present_in_compound_builder() -> None:
    prompt = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic one",
        secondary_input="brief two",
    )
    assert DESTRUCTIVE_FILE_DELETE_TOKEN in prompt
    assert DESTRUCTIVE_FORCE_PUSH_TOKEN in prompt
    assert DESTRUCTIVE_DROP_DATABASE_TOKEN in prompt


@pytest.mark.unit
def test_boundary_line_precedes_user_idea() -> None:
    prompt = phase1_prompt_builder(_specialist(), _spec(), idea_text="Build app", role="primary")
    assert prompt.index(BOUNDARY_LINE) < prompt.index("<USER_IDEA>")

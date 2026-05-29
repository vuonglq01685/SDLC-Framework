"""Unit tests for nonce coupling + destructive-block scoping (Story 2B.6 Tasks 4+5).

RED phase: these tests prove the desired behaviours before the implementation exists.

Task 4 (CR2B5-W1):
- phase1_prompt_builder accepts a ``nonce`` kwarg
- When nonce is provided, the nonce appears in the destructive-ops block
- When nonce is omitted, the static tokens still appear (backward-compat)
- phase1_compound_prompt_builder has the same nonce kwarg

Task 5 (CR2B5-W2):
- A specialist with empty write_globs does NOT get the destructive block
- A specialist whose every glob is under _bmad-output/ does NOT get the block
- A specialist with at least one glob outside _bmad-output/ DOES get the block
- _should_inject_destructive_block is exported and testable
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.prompts import (
    DESTRUCTIVE_DROP_DATABASE_TOKEN,
    DESTRUCTIVE_FILE_DELETE_TOKEN,
    DESTRUCTIVE_FORCE_PUSH_TOKEN,
    phase1_compound_prompt_builder,
    phase1_prompt_builder,
)
from sdlc.dispatcher.safety import _should_inject_destructive_block
from sdlc.specialists.frontmatter import Specialist


def _spec() -> WorkflowSpec:
    return WorkflowSpec(
        schema_version=1,
        name="phase1-product-discovery",
        slash_command="/sdlc-start",
        primary_agent="product-strategist",
        parallel_agents=(),
        synthesizer_agent=None,
        write_globs={"product-strategist": ("01-Requirement/01-PRODUCT.md",)},
    )


def _specialist(write_globs: tuple[str, ...] = ("01-Requirement/01-PRODUCT.md",)) -> Specialist:
    fm = SpecialistFrontmatter(
        schema_version=1,
        name="product-strategist",
        title="Product Strategist",
        icon="🎯",
        model="sonnet",
        description="Strategy.",
        write_globs=write_globs,
    )
    return Specialist(frontmatter=fm, body="Do the thing.", source_path=Path(__file__))


def _bmad_specialist() -> Specialist:
    return _specialist(write_globs=("_bmad-output/foo/bar.md",))


def _readonly_specialist() -> Specialist:
    return _specialist(write_globs=())


# ---------------------------------------------------------------------------
# Task 4: nonce kwarg on phase1_prompt_builder
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_phase1_prompt_builder_accepts_nonce_kwarg() -> None:
    """phase1_prompt_builder accepts a nonce kwarg without raising."""
    prompt = phase1_prompt_builder(
        _specialist(), _spec(), idea_text="Build app", role="primary", nonce="test-nonce-abc"
    )
    assert isinstance(prompt, str)


@pytest.mark.unit
def test_phase1_prompt_builder_nonce_appears_in_prompt() -> None:
    """When nonce is supplied, it appears inside the destructive-ops block."""
    nonce = "abc123xyz-unique-nonce"
    prompt = phase1_prompt_builder(
        _specialist(), _spec(), idea_text="Build app", role="primary", nonce=nonce
    )
    assert nonce in prompt


@pytest.mark.unit
def test_phase1_prompt_builder_nonce_qualifies_static_tokens() -> None:
    """With a nonce, static tokens are qualified so they are no longer predictable."""
    nonce = "random-nonce-99"
    prompt_with_nonce = phase1_prompt_builder(
        _specialist(), _spec(), idea_text="Build app", role="primary", nonce=nonce
    )
    # With nonce → nonce appears AND the static tokens carry the per-dispatch
    # suffix (the bare static token is no longer emitted in v2 — CR2B5-W1 is
    # closed via the post-review D1+D2 hardening).
    assert nonce in prompt_with_nonce
    assert f"{DESTRUCTIVE_FILE_DELETE_TOKEN}_{nonce}" in prompt_with_nonce


@pytest.mark.unit
def test_phase1_prompt_builder_no_nonce_emits_static_block_v1() -> None:
    """V1 architectural pivot: when no nonce is supplied, the destructive-ops
    block emits the STATIC tokens (same as 2B.5 baseline). Per-dispatch
    nonce-suffixed tokens are reserved for the (future) agent-side
    verification work — see EPIC-2B-DEBT-NONCE-VERIFICATION-AGENT-SIDE.
    """
    prompt = phase1_prompt_builder(_specialist(), _spec(), idea_text="Build app", role="primary")
    assert "<DESTRUCTIVE_OPS>" in prompt
    assert DESTRUCTIVE_FILE_DELETE_TOKEN in prompt
    assert DESTRUCTIVE_FORCE_PUSH_TOKEN in prompt
    assert DESTRUCTIVE_DROP_DATABASE_TOKEN in prompt


@pytest.mark.unit
def test_phase1_prompt_builder_with_nonce_includes_qualified_block_d1_d2() -> None:
    """With nonce supplied, the destructive-ops block is emitted with
    per-dispatch suffix on every token (no bare static token remains).
    """
    nonce = "session-nonce-abc"
    prompt = phase1_prompt_builder(
        _specialist(), _spec(), idea_text="Build app", role="primary", nonce=nonce
    )
    assert "<DESTRUCTIVE_OPS>" in prompt
    assert f"{DESTRUCTIVE_FILE_DELETE_TOKEN}_{nonce}" in prompt
    assert f"{DESTRUCTIVE_FORCE_PUSH_TOKEN}_{nonce}" in prompt
    assert f"{DESTRUCTIVE_DROP_DATABASE_TOKEN}_{nonce}" in prompt


@pytest.mark.unit
def test_phase1_prompt_builder_readonly_specialist_does_not_need_nonce_d1_d2() -> None:
    """Read-only specialists skip the destructive block; nonce is not required."""
    prompt = phase1_prompt_builder(
        _readonly_specialist(), _spec(), idea_text="Build app", role="primary"
    )
    assert "<DESTRUCTIVE_OPS>" not in prompt


@pytest.mark.unit
def test_phase1_compound_builder_accepts_nonce_kwarg() -> None:
    """phase1_compound_prompt_builder accepts a nonce kwarg without raising."""
    prompt = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic text",
        secondary_input="brief text",
        nonce="test-nonce-xyz",
    )
    assert isinstance(prompt, str)


@pytest.mark.unit
def test_phase1_compound_builder_nonce_appears_in_prompt() -> None:
    """When nonce is supplied to compound builder, it appears in the prompt."""
    nonce = "compound-nonce-55"
    prompt = phase1_compound_prompt_builder(
        _specialist(),
        _spec(),
        primary_input="epic text",
        secondary_input="brief text",
        nonce=nonce,
    )
    assert nonce in prompt


# ---------------------------------------------------------------------------
# Task 5: _should_inject_destructive_block scoping predicate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_should_inject_true_for_non_bmad_glob() -> None:
    """Specialist with a non-_bmad-output/ glob → inject destructive block."""
    assert _should_inject_destructive_block(_specialist()) is True


@pytest.mark.unit
def test_should_inject_false_for_empty_write_globs() -> None:
    """Read-only specialist (empty write_globs) → do NOT inject destructive block."""
    assert _should_inject_destructive_block(_readonly_specialist()) is False


@pytest.mark.unit
def test_should_inject_false_for_all_bmad_output_globs() -> None:
    """Specialist whose every glob is under _bmad-output/ → do NOT inject."""
    assert _should_inject_destructive_block(_bmad_specialist()) is False


@pytest.mark.unit
def test_should_inject_true_when_mixed_globs() -> None:
    """Specialist with one bmad + one non-bmad glob → DO inject (any non-bmad triggers)."""
    s = _specialist(write_globs=("_bmad-output/foo.md", "src/app/main.py"))
    assert _should_inject_destructive_block(s) is True


@pytest.mark.unit
def test_phase1_prompt_no_destructive_block_for_readonly_specialist() -> None:
    """phase1_prompt_builder does NOT include destructive-ops block for read-only specialist."""
    prompt = phase1_prompt_builder(
        _readonly_specialist(),
        _spec(),
        idea_text="Build app",
        role="primary",
        nonce="readonly-test-nonce",
    )
    assert DESTRUCTIVE_FILE_DELETE_TOKEN not in prompt
    assert DESTRUCTIVE_FORCE_PUSH_TOKEN not in prompt
    assert DESTRUCTIVE_DROP_DATABASE_TOKEN not in prompt
    assert "<DESTRUCTIVE_OPS>" not in prompt


@pytest.mark.unit
def test_phase1_prompt_no_destructive_block_for_bmad_only_specialist() -> None:
    """phase1_prompt_builder omits destructive-ops block for _bmad-output/-only globs."""
    prompt = phase1_prompt_builder(
        _bmad_specialist(),
        _spec(),
        idea_text="Build app",
        role="primary",
        nonce="bmad-test-nonce",
    )
    assert DESTRUCTIVE_FILE_DELETE_TOKEN not in prompt
    assert "<DESTRUCTIVE_OPS>" not in prompt


@pytest.mark.unit
def test_phase1_compound_no_destructive_block_for_readonly_specialist() -> None:
    """phase1_compound_prompt_builder omits destructive-ops block for read-only specialist."""
    prompt = phase1_compound_prompt_builder(
        _readonly_specialist(),
        _spec(),
        primary_input="epic",
        secondary_input="brief",
        nonce="compound-readonly-test-nonce",
    )
    assert DESTRUCTIVE_FILE_DELETE_TOKEN not in prompt
    assert "<DESTRUCTIVE_OPS>" not in prompt

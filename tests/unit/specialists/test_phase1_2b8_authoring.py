"""Story 2B.8 — AC6 anti-tautology receipts (positive + negative).

RED-before-GREEN ordering (CONTRIBUTING §2):
  - Positive receipts fail RED until Task 3+4 (author + manifest) are done.
  - Boundary-line receipts fail RED until Task 2+3 (re-author bodies) are done.
  - Placeholder-marker test fails RED until Task 2+3 (replace stub content) done.
  - Negative receipts prove the 2A.2 validator CAN reject; they pass from the start.

Anti-tautology (ADR-026 §1):
  - Negative receipts prove the validator gate can fail (not just pass vacuously).
  - Positive receipts prove new files actually loaded (not just absence-of-error).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.dispatcher.prompts import BOUNDARY_LINE
from sdlc.errors import SpecialistError
from sdlc.specialists import load_registry
from sdlc.specialists.frontmatter import load_specialist

_REPO = Path(__file__).resolve().parents[3]
_AGENTS = _REPO / "src" / "sdlc" / "agents"
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "markdown"

# The 7 net-new Phase-1 specialists authored in Story 2B.8 (D1=(a)).
_NET_NEW_PHASE1_NAMES: frozenset[str] = frozenset(
    {
        "requirement-analyst",
        "market-researcher",
        "stakeholder-simulator",
        "dependency-mapper",
        "prioritizer",
        "acceptance-criteria-author",
        "story-prioritizer",
    }
)

# All Phase-1 specialist names (8 re-authored stubs + 7 net-new = 15 total).
_ALL_PHASE1_NAMES: frozenset[str] = (
    frozenset(
        {
            "product-strategist",
            "technical-researcher",
            "devil-advocate",
            "requirement-synthesizer",
            "artifact-verifier",
            "epic-generator",
            "story-writer",
            "phase1-signoff-summarizer",
        }
    )
    | _NET_NEW_PHASE1_NAMES
)

# Placeholder marker substrings that must NOT appear in any Phase-1 body
# after 2B.8. Used by AC1 + no-placeholder test.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "Phase 1 placeholder",
    "Replaced by Story 2B.8",
    "placeholder until Story",
    "v1 stub — NOT dispatched",
    "Placeholder until Story 2B",
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AC6 Positive receipts — net-new specialists must be in the registry.
# These fail RED until Task 3 (authoring) + Task 4 (manifest) are complete.
# ---------------------------------------------------------------------------


def test_net_new_phase1_specialists_load_via_registry() -> None:
    """AC6 positive receipt: load_registry includes all 7 net-new Phase-1 names.

    Fails RED until requirement-analyst, market-researcher, stakeholder-simulator,
    dependency-mapper, prioritizer, acceptance-criteria-author, story-prioritizer
    are authored + registered in src/sdlc/agents/.
    """
    reg = load_registry(_AGENTS)
    missing = _NET_NEW_PHASE1_NAMES - reg.names()
    assert not missing, (
        f"Net-new Phase-1 specialists not found in registry: {sorted(missing)!r}. "
        "Complete Task 3 (authoring) + Task 4 (manifest) to satisfy AC6."
    )


def test_net_new_phase1_specialists_have_correct_phase() -> None:
    """AC6: every net-new Phase-1 specialist carries phase=1 in the registry."""
    reg = load_registry(_AGENTS)
    wrong_phase = []
    for name in _NET_NEW_PHASE1_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            wrong_phase.append(f"{name!r}: not found in registry")
            continue
        if s.phase != 1:
            wrong_phase.append(f"{name!r}: phase={s.phase!r}, expected 1")
    assert not wrong_phase, "\n".join(wrong_phase)


def test_net_new_phase1_schema_version_is_one() -> None:
    """AC3: every net-new specialist frontmatter has schema_version=1.

    SpecialistFrontmatter.schema_version is Literal[1] — the registry loader
    would have already rejected the file if this were not satisfied. This test
    proves the files parsed successfully through the contract validator.
    """
    reg = load_registry(_AGENTS)
    missing = []
    for name in _NET_NEW_PHASE1_NAMES:
        try:
            s = reg.get(name)
            # schema_version is Literal[1] — if load succeeded, the contract is met.
            assert s.frontmatter.schema_version == 1
        except SpecialistError:
            missing.append(f"{name!r}: not found in registry")
    assert not missing, "\n".join(missing)


# ---------------------------------------------------------------------------
# AC4 / AC6 Boundary-line architectural invariant.
#
# Architecture clarification (discovered during 2B.8 implementation):
# phase1_prompt_builder (dispatcher/prompts.py:241) REJECTS specialist bodies
# that already contain BOUNDARY_LINE — the builder injects it automatically
# into the compiled prompt between <INSTRUCTIONS> and <USER_IDEA>.
# Every Phase-1 compiled prompt therefore contains BOUNDARY_LINE by virtue
# of phase1_prompt_builder, satisfying AC4 architecturally.
# D2=(a) is correct (author-by-convention); D2=(b) is architecturally wrong.
#
# The test below verifies the architectural invariant: no Phase-1 body may
# contain BOUNDARY_LINE, ensuring the builder will not reject any specialist.
# ---------------------------------------------------------------------------


def test_no_phase1_body_contains_boundary_line() -> None:
    """AC4 architectural invariant: no Phase-1 body contains BOUNDARY_LINE.

    The phase1_prompt_builder (dispatcher/prompts.py:241) raises WorkflowError
    if a specialist body contains BOUNDARY_LINE — the builder injects it at
    the correct position (between <INSTRUCTIONS> and <USER_IDEA>) automatically.
    This test ensures the body/builder split is respected for all Phase-1
    specialists (both re-authored stubs and net-new).
    """
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE1_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not in registry — author or register it first")
            continue
        if BOUNDARY_LINE in s.body:
            violations.append(
                f"{name!r}: body contains BOUNDARY_LINE — builder will reject this "
                "(BOUNDARY_LINE is injected by phase1_prompt_builder, not the body)"
            )
    assert not violations, (
        "Phase-1 specialist bodies illegally contain BOUNDARY_LINE:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# AC1: No placeholder markers remain in any Phase-1 file after 2B.8.
# Fails RED until Task 2 (re-author stubs) + Task 3 (net-new) are complete.
# ---------------------------------------------------------------------------


def test_no_phase1_body_contains_placeholder_marker() -> None:
    """AC1: no Phase-1 specialist body/description retains placeholder text."""
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE1_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            continue  # Registry absence caught by positive-receipt test above
        desc = s.frontmatter.description
        body = s.body
        for marker in _PLACEHOLDER_MARKERS:
            if marker.lower() in body.lower() or marker.lower() in desc.lower():
                violations.append(f"{name!r}: contains placeholder marker {marker!r}")
                break
    assert not violations, "Phase-1 specialists still contain placeholder content:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# AC6 Negative receipts — the 2A.2 frontmatter validator MUST reject malformed
# files. These PASS from the start; their purpose is to prove the gate CAN fail.
# ---------------------------------------------------------------------------


def test_malformed_specialist_icon_too_long_rejected() -> None:
    """AC6 negative receipt: icon with >4 chars (ABCDE) raises SpecialistError.

    Proves the SpecialistFrontmatter icon max_length=4 gate is load-bearing,
    not vacuous (anti-tautology per ADR-026 §1).
    """
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "icon-too-long.md")


def test_malformed_specialist_missing_description_rejected() -> None:
    """AC6 negative receipt: absent description field raises SpecialistError.

    Proves the SpecialistFrontmatter required-field gate is load-bearing
    (anti-tautology per ADR-026 §1).
    """
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "missing-description.md")

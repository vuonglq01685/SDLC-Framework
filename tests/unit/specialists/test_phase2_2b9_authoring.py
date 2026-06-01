"""Story 2B.9 — AC anti-tautology receipts for Phase-2 specialist authoring.

RED-before-GREEN ordering (CONTRIBUTING §2):
  - Positive receipts (new names in registry) fail RED until T3+T4 (author + manifest).
  - Placeholder-marker test fails RED until T2+T3 (replace stub bodies).
  - Boundary-line invariant test passes from the start (architectural constraint).
  - No-api-architect invariant passes from the start (D2=(a) constraint).
  - Negative receipts prove the 2A.2 validator CAN reject; they pass from the start.

Anti-tautology (ADR-026 §1):
  - Negative receipts prove the validator gate can fail (not just pass vacuously).
  - Positive receipts prove new files actually loaded (not just absence-of-error).

Decision record (T0):
  D1=(b): enrich 6 existing stubs + author 6 new planned = 12 files total.
  D2=(a): api-designer only; api-architect must NOT be registered.
  D3=(a): full ux-reviewer production prompt (close EPIC-2A-DEBT-UX-PARALLEL-REVIEWER).
  D4: ship matrix names verbatim (no renames).
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

# All 6 existing Phase-2 specialist names (to be enriched — D1=(b)).
_EXISTING_PHASE2_NAMES: frozenset[str] = frozenset(
    {
        "system-architect",
        "database-architect",
        "security-architect",
        "observability-architect",
        "ux-designer",
        "ux-reviewer",
    }
)

# The 6 net-new Phase-2 specialists authored in Story 2B.9 (matrix §3, D1=(b)).
_NET_NEW_PHASE2_NAMES: frozenset[str] = frozenset(
    {
        "ux-researcher",
        "design-system-author",
        "a11y-reviewer",
        "infra-architect",
        "devex-architect",
        "api-designer",
    }
)

# All Phase-2 specialist names (6 enriched + 6 net-new = 12 total per D1=(b)).
_ALL_PHASE2_NAMES: frozenset[str] = _EXISTING_PHASE2_NAMES | _NET_NEW_PHASE2_NAMES

# Placeholder marker substrings that must NOT appear in any Phase-2 body
# after 2B.9. Used by AC1 + no-placeholder test.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "Phase 2 placeholder",
    "Replaced by Story 2B.9",
    "placeholder until Story 2B.9",
    "Placeholder until Story 2B.9",
    "MockAIRuntime v1",
    "PLACEHOLDER",
    "EPIC-2A-DEBT-UX-PARALLEL-REVIEWER",
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AC2 Positive receipts — net-new Phase-2 specialists must be in registry.
# These fail RED until T3 (authoring) + T4 (manifest rows) are complete.
# ---------------------------------------------------------------------------


def test_net_new_phase2_specialists_load_via_registry() -> None:
    """AC2 positive receipt: load_registry includes all 6 net-new Phase-2 names.

    Fails RED until ux-researcher, design-system-author, a11y-reviewer,
    infra-architect, devex-architect, api-designer are authored + registered
    in src/sdlc/agents/index.yaml.
    """
    reg = load_registry(_AGENTS)
    missing = _NET_NEW_PHASE2_NAMES - reg.names()
    assert not missing, (
        f"Net-new Phase-2 specialists not found in registry: {sorted(missing)!r}. "
        "Complete T3 (authoring) + T4 (manifest rows) to satisfy AC2."
    )


def test_net_new_phase2_specialists_have_correct_phase() -> None:
    """AC6: every net-new Phase-2 specialist carries phase=2 in the registry."""
    reg = load_registry(_AGENTS)
    wrong_phase = []
    for name in _NET_NEW_PHASE2_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            wrong_phase.append(f"{name!r}: not found in registry")
            continue
        if s.phase != 2:
            wrong_phase.append(f"{name!r}: phase={s.phase!r}, expected 2")
    assert not wrong_phase, "\n".join(wrong_phase)


def test_net_new_phase2_schema_version_is_one() -> None:
    """AC3: every net-new specialist frontmatter has schema_version=1."""
    reg = load_registry(_AGENTS)
    violations = []
    for name in _NET_NEW_PHASE2_NAMES:
        try:
            s = reg.get(name)
            assert s.frontmatter.schema_version == 1
        except SpecialistError:
            violations.append(f"{name!r}: not found in registry")
    assert not violations, "\n".join(violations)


# ---------------------------------------------------------------------------
# AC1: No placeholder markers remain in any Phase-2 file after 2B.9.
# Fails RED until T2 (enrich existing stubs) + T3 (author new files) done.
# ---------------------------------------------------------------------------


def test_no_phase2_body_contains_placeholder_marker() -> None:
    """AC1: no Phase-2 specialist body/description retains placeholder text.

    Fails RED until all existing stubs (T2) and new specialists (T3) carry
    production prompts with no PLACEHOLDER or MockAIRuntime wording.
    """
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE2_NAMES:
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
    assert not violations, "Phase-2 specialists still contain placeholder content:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# AC4 / AC3 Boundary-line architectural invariant (passes from the start).
#
# Architecture clarification (mirrored from 2B.8 findings):
# phase1_prompt_builder (dispatcher/prompts.py) REJECTS specialist bodies that
# already contain BOUNDARY_LINE — the builder injects it automatically between
# <INSTRUCTIONS> and <USER_IDEA>. Every compiled prompt therefore contains
# BOUNDARY_LINE by virtue of phase1_prompt_builder, satisfying AC4 architecturally.
# Specialist bodies (both Phase-1 and Phase-2, since architect.py uses
# phase1_prompt_builder) must NOT contain BOUNDARY_LINE.
# ---------------------------------------------------------------------------


def test_no_phase2_body_contains_boundary_line() -> None:
    """AC4 architectural invariant: no Phase-2 body contains BOUNDARY_LINE.

    The phase1_prompt_builder raises WorkflowError if a specialist body
    contains BOUNDARY_LINE — the builder injects it at the correct position.
    Phase-2 dispatch (sdlc/cli/architect.py) also uses phase1_prompt_builder.
    """
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE2_NAMES:
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
        "Phase-2 specialist bodies illegally contain BOUNDARY_LINE:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# AC9 / D2=(a): api-architect must NOT be registered (D2=(a) invariant).
# Passes from the start — prevents accidental api-architect creation.
# ---------------------------------------------------------------------------


def test_no_api_architect_in_registry() -> None:
    """AC9/D2=(a): api-architect must never be registered.

    The frozen matrix (ADR-030) has no api-architect row; the planned
    wire-format role is api-designer. D2=(a) was chosen: api-architect
    is a non-existent/unconfirmed name and must not appear in the registry.
    """
    reg = load_registry(_AGENTS)
    assert "api-architect" not in reg.names(), (
        "api-architect was registered but D2=(a) forbids it. "
        "The correct planned name is api-designer (matrix §3). "
        "Remove the api-architect row from index.yaml and delete any api-architect.md."
    )


# ---------------------------------------------------------------------------
# AC5 / No tool escalation: tools must remain [] for all Phase-2 specialists.
# Fails RED until T2+T3 when new files carry correct frontmatter.
# ---------------------------------------------------------------------------


def test_phase2_specialists_have_empty_tools() -> None:
    """AC5: every Phase-2 specialist frontmatter has tools=[] (no escalation).

    Matches the existing Phase-2 convention: capability is expressed via
    read_globs/write_globs, not a tool allow-list. No file may declare
    a destructive/exec capability via tools.
    """
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE2_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            continue  # Absence caught by positive-receipt test
        if s.frontmatter.tools:
            violations.append(
                f"{name!r}: tools={s.frontmatter.tools!r}, expected [] (no escalation)"
            )
    assert not violations, (
        "Phase-2 specialists have non-empty tools (AC5 escalation):\n"
        + "\n".join(f"  - {v}" for v in violations)
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

"""Story 2B.11 — AC13 anti-tautology receipts for support specialist authoring.

RED-before-GREEN ordering (CONTRIBUTING §2):
  - Positive receipts (new names in registry) fail RED until T5+T6 (author + manifest).
  - Placeholder-marker test fails RED until T5 (author new files with production bodies).
  - Boundary-line invariant passes from the start (architectural constraint).
  - Count-gate test fails RED until T5+T6 (support files + index.yaml entries land).
  - Workflow-ref gate may pass from the start (standing regression gate on existing refs).
  - Negative receipts prove the 2A.2 validator CAN reject; they pass from the start.

Anti-tautology (ADR-026 §1):
  - Negative receipts prove the validator gate can fail (not just pass vacuously).
  - Positive receipts prove new files actually loaded (not just absence-of-error).

Decision record (T0):
  D1=(a): 3 genuinely net-new: clarification-triager, agent-failure-recovery,
           orchestrator-helper. devil-advocate/synthesizer/signoff-summarizer staffed-by-shipped.
  D2=(a): New src/sdlc/agents/support/ dir, phase: 0 (cross-cutting support phase).
  D3=(a): Count bound re-derived from matrix: 39 shipped → band ≥35, ≤45.
  D4=(a): Re-use test_abstraction_adequacy.py green as ship signal (fixture-scoped).
  D5=(a): Hand-update matrix + add consistency test pinning rows ↔ index.yaml.
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
_WORKFLOWS = _REPO / "src" / "sdlc" / "workflows_yaml"
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "markdown"

# The 3 genuinely net-new support specialists authored in Story 2B.11 (D1=(a)).
_NET_NEW_SUPPORT_NAMES: frozenset[str] = frozenset(
    {
        "clarification-triager",
        "agent-failure-recovery",
        "orchestrator-helper",
    }
)

# Placeholder marker substrings that must NOT appear in any support body.
# CR2B8-W1/CR2B9-W1 hardening: append violations instead of silently continuing.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "support placeholder",
    "Replaced by Story 2B.11",
    "placeholder until Story 2B.11",
    "MockAIRuntime v1",
    "**PLACEHOLDER**",
)

# D3=(a): count bound re-derived from matrix after 2B.11.
# Pre-2B.11 roster = 36; +3 support = 39 shipped. Lower bound = 39 (exact
# post-2B.11 minimum) so the gate fails RED until all 3 support files land.
# Upper bound = 45 tolerates near-future small additions.
_ROSTER_LOW: int = 39
_ROSTER_HIGH: int = 45

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AC2 Positive receipts — net-new support specialists must be in registry.
# These fail RED until T5 (author files) + T6 (manifest rows) are complete.
# ---------------------------------------------------------------------------


def test_net_new_support_specialists_load_via_registry() -> None:
    """AC2 positive receipt: load_registry includes all 3 net-new support names.

    Fails RED until clarification-triager, agent-failure-recovery,
    orchestrator-helper are authored + registered in src/sdlc/agents/index.yaml.
    """
    reg = load_registry(_AGENTS)
    missing = _NET_NEW_SUPPORT_NAMES - reg.names()
    assert not missing, (
        f"Net-new support specialists not found in registry: {sorted(missing)!r}. "
        "Complete T5 (authoring) + T6 (manifest rows) to satisfy AC2."
    )


def test_net_new_support_specialists_have_correct_phase() -> None:
    """AC2/D2=(a): every net-new support specialist carries phase=0 in the registry."""
    reg = load_registry(_AGENTS)
    violations: list[str] = []
    for name in _NET_NEW_SUPPORT_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not found in registry")
            continue
        if s.phase != 0:
            violations.append(f"{name!r}: phase={s.phase!r}, expected 0 (cross-cutting support)")
    assert not violations, "\n".join(violations)


def test_net_new_support_schema_version_is_one() -> None:
    """AC3: every net-new support specialist frontmatter has schema_version=1.

    Report-all aggregation (CR2B9-P1): AssertionError must not escape the
    SpecialistError handler and abort the loop on the first offender.
    """
    reg = load_registry(_AGENTS)
    violations: list[str] = []
    for name in _NET_NEW_SUPPORT_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not found in registry")
            continue
        if s.frontmatter.schema_version != 1:
            violations.append(
                f"{name!r}: schema_version={s.frontmatter.schema_version!r}, expected 1"
            )
    assert not violations, "\n".join(violations)


# ---------------------------------------------------------------------------
# AC1 / AC13: No placeholder markers remain in any support body.
# Fails RED until T5 (author files with production content) is complete.
# ---------------------------------------------------------------------------


def test_no_support_body_contains_placeholder_marker() -> None:
    """AC1/AC13: no support specialist body/description retains placeholder text.

    CR2B8-W1/CR2B9-W1 hardening: registry absence appends a violation instead
    of silently continuing — prevents a broken stub from being skipped silently.
    """
    reg = load_registry(_AGENTS)
    violations: list[str] = []
    for name in _NET_NEW_SUPPORT_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not in registry — cannot check placeholder markers")
            continue
        desc = s.frontmatter.description
        body = s.body
        for marker in _PLACEHOLDER_MARKERS:
            if marker.lower() in body.lower() or marker.lower() in desc.lower():
                violations.append(f"{name!r}: contains placeholder marker {marker!r}")
                break
    assert not violations, "Support specialists still contain placeholder content:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# AC6 / AC13: Boundary-line architectural invariant (passes from the start).
# BOUNDARY_LINE must be ABSENT from bodies — the prompt builder injects it.
# ---------------------------------------------------------------------------


def test_no_support_body_contains_boundary_line() -> None:
    """AC6/AC13 architectural invariant: no support body contains BOUNDARY_LINE.

    phase1_prompt_builder (prompts.py:241) raises WorkflowError if a specialist
    body already contains BOUNDARY_LINE — the builder injects it between
    <INSTRUCTIONS> and <USER_IDEA>. Absence is required per AC6.
    """
    reg = load_registry(_AGENTS)
    violations: list[str] = []
    for name in _NET_NEW_SUPPORT_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not in registry — cannot check boundary line")
            continue
        if BOUNDARY_LINE in s.body:
            violations.append(
                f"{name!r}: body contains BOUNDARY_LINE — builder will reject this "
                "(BOUNDARY_LINE is injected by the prompt builder, not the body)"
            )
    assert not violations, (
        "Support specialist bodies illegally contain BOUNDARY_LINE:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# AC2 / tools=[]: support specialists declare no tool escalation.
# ---------------------------------------------------------------------------


def test_support_specialists_have_empty_tools() -> None:
    """AC2: every support specialist frontmatter has tools=[] (no escalation).

    Support roles are registered-but-not-dispatched-in-v1; they declare no
    Bash/network/destructive capability.
    """
    reg = load_registry(_AGENTS)
    violations: list[str] = []
    for name in _NET_NEW_SUPPORT_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            continue  # Absence caught by positive-receipt test above
        if s.frontmatter.tools:
            violations.append(
                f"{name!r}: tools={s.frontmatter.tools!r}, expected [] (no escalation)"
            )
    assert not violations, "Support specialists have non-empty tools:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# AC7 / D3=(a): Count gate — closes CR2B10-W8. RED until support files land.
# ---------------------------------------------------------------------------


def test_specialist_roster_count_within_bound() -> None:
    """AC7/D3=(a): full roster size is within the re-derived bound [35, 45].

    Pre-2B.11 roster = 36 (15 P1 + 12 P2 + 9 P3); +3 support = 39 shipped.
    Band ≥35 ≤45 tolerates near-future small additions (matrix is authoritative;
    see docs/sprints/epic-2b-dag.md §3 + ADR-030 amendment for numeric record).
    Fails RED until support files + index.yaml entries exist (count < 39).
    """
    reg = load_registry(_AGENTS)
    count = len(reg.names())
    assert _ROSTER_LOW <= count <= _ROSTER_HIGH, (
        f"Specialist roster count {count} is outside re-derived band "
        f"[{_ROSTER_LOW}, {_ROSTER_HIGH}]. "
        "Update _ROSTER_LOW/_ROSTER_HIGH if the matrix target changed "
        "(document in docs/sprints/epic-2b-dag.md §3 + ADR-030 amendment)."
    )


# ---------------------------------------------------------------------------
# AC8: Workflow YAML reference gate — standing regression test.
# Loads all 11 real workflow specs and validates every specialist ref resolves.
# May pass from the start (existing refs already resolve); stays green after 2B.11.
# ---------------------------------------------------------------------------


def test_all_workflow_yaml_specialist_refs_resolve() -> None:
    """AC8: every specialist reference in all 11 workflow YAMLs resolves.

    Skips the 'none' primary_agent sentinel (sdlc-signoff.yaml) which is not a
    specialist name. This is a standing regression gate — any future workflow
    that references a misspelled or unregistered specialist will be caught here.
    """
    from sdlc.errors import SpecialistError as _SE
    from sdlc.specialists.validator import validate_workflow_refs
    from sdlc.workflows.registry import WorkflowRegistry

    workflow_registry = WorkflowRegistry.load(_WORKFLOWS)
    specialist_registry = load_registry(_AGENTS)

    violations: list[str] = []
    for spec in workflow_registry.list():
        if spec.primary_agent == "none":
            continue  # sdlc-signoff.yaml sentinel — not a specialist
        try:
            validate_workflow_refs(spec, specialist_registry)
        except _SE as exc:
            violations.append(str(exc))

    assert not violations, (
        "Workflow YAML files contain unresolved specialist references:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# AC13 Negative receipts — the frontmatter validator MUST reject malformed files.
# These PASS from the start; they prove the gate CAN fail (anti-tautology).
# ---------------------------------------------------------------------------


def test_malformed_specialist_icon_too_long_rejected() -> None:
    """AC13 negative receipt: icon with >4 chars (ABCDE) raises SpecialistError.

    Proves the SpecialistFrontmatter icon max_length=4 gate is load-bearing,
    not vacuous (anti-tautology per ADR-026 §1).
    """
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "icon-too-long.md")


def test_malformed_specialist_missing_description_rejected() -> None:
    """AC13 negative receipt: absent description field raises SpecialistError.

    Proves the SpecialistFrontmatter required-field gate is load-bearing
    (anti-tautology per ADR-026 §1).
    """
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "missing-description.md")

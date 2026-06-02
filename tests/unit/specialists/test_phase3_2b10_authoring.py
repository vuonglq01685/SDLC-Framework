"""Story 2B.10 — anti-tautology receipts for Phase-3 specialist authoring.

RED-before-GREEN ordering (CONTRIBUTING §2):
  - Positive receipts (new names) fail RED until T7+T8 (author + manifest).
  - Placeholder-marker test fails RED until T3-T6 (re-author stubs) are done.
  - Boundary-line invariant passes from start (architectural constraint).
  - Pipeline-map invariants pass from start (_task_pipeline.py is frozen 2A.17).
  - Negative receipts prove the validator CAN reject; pass from the start.

Decisions locked (T0):
  D1=(a): Author all 4 NEW — pr-author, tdd-strategist, security-reviewer,
           edge-case-reviewer — closes Phase-3 planned rows in matrix §3.
  D2=(a): Enrich code-bootstrapper + task-breaker (full Phase-3 group).
  D3=(a): code-author as conformance representative (AC9).
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

# 5 existing Phase-3 stubs enriched in 2B.10 (D2=(a): all 5).
_EXISTING_PHASE3_NAMES: frozenset[str] = frozenset(
    {"test-author", "code-author", "code-reviewer", "code-bootstrapper", "task-breaker"}
)

# 4 net-new Phase-3 specialists authored in 2B.10 (matrix §3, D1=(a)).
_NET_NEW_PHASE3_NAMES: frozenset[str] = frozenset(
    {"pr-author", "tdd-strategist", "security-reviewer", "edge-case-reviewer"}
)

# Story 3.8 — net-new brownfield characterization-test author (D1=(a)). Folded into the
# shared Phase-3 invariant sweep (boundary line / placeholder / empty tools / phase / name).
_PHASE3_38_NAMES: frozenset[str] = frozenset({"characterization-author"})

# All Phase-3 names: 5 enriched + 4 net-new (2B.10) + 1 brownfield (3.8).
_ALL_PHASE3_NAMES: frozenset[str] = (
    _EXISTING_PHASE3_NAMES | _NET_NEW_PHASE3_NAMES | _PHASE3_38_NAMES
)

# TDD pipeline dispatched specialists (frozen in _task_pipeline.py, Story 2A.17).
_PIPELINE_DISPATCHED: frozenset[str] = frozenset({"test-author", "code-author", "code-reviewer"})

# Delivery specialists that must NOT be in _STAGE_SPECIALIST (AC10).
_POST_PIPELINE: frozenset[str] = frozenset(
    {"pr-author", "tdd-strategist", "security-reviewer", "edge-case-reviewer"}
)

# Placeholder markers that must be absent from all Phase-3 bodies after 2B.10.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "Phase 3 placeholder",
    "Replaced by Story 2B.10",
    "MockAIRuntime v1",
    "**PLACEHOLDER**",
    "placeholder until Story",
)

# JSON contract keywords each TDD-pipeline specialist must declare in its body.
_TDD_RED_REQUIRED: tuple[str, ...] = ('"tests_status"', '"red"', '"files"')
_TDD_GREEN_REQUIRED: tuple[str, ...] = ('"tests_status"', '"green"', '"files"')
_REVIEW_REQUIRED: tuple[str, ...] = ('"verdict"', '"approved"', '"rejected"', '"notes"')

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Positive receipts — fail RED until authoring + manifest rows are done.
# ---------------------------------------------------------------------------


def test_net_new_phase3_specialists_load_via_registry() -> None:
    """AC6: load_registry includes all 4 net-new Phase-3 names.

    Fails RED until pr-author, tdd-strategist, security-reviewer, edge-case-reviewer
    are authored + registered in src/sdlc/agents/index.yaml (T7+T8).
    """
    reg = load_registry(_AGENTS)
    missing = _NET_NEW_PHASE3_NAMES - reg.names()
    assert not missing, (
        f"Net-new Phase-3 specialists not found in registry: {sorted(missing)!r}. "
        "Complete T7 (authoring) + T8 (manifest rows) to satisfy AC6."
    )


def test_all_phase3_names_in_registry() -> None:
    """AC5/AC6: registry contains ALL 9 Phase-3 names (5 enriched + 4 new).

    Fails RED until all stubs are enriched (T3-T6) and new files authored (T7+T8).
    """
    reg = load_registry(_AGENTS)
    missing = _ALL_PHASE3_NAMES - reg.names()
    assert not missing, (
        f"Phase-3 specialists absent from registry: {sorted(missing)!r}. "
        "Enrich stubs (T3-T6) + author new files (T7) + update index.yaml (T8)."
    )


def test_all_phase3_phase_field_is_3() -> None:
    """AC5/AC6: every Phase-3 entry carries phase=3 in the registry."""
    reg = load_registry(_AGENTS)
    wrong = []
    for name in _ALL_PHASE3_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            wrong.append(f"{name!r}: not in registry")
            continue
        if s.phase != 3:
            wrong.append(f"{name!r}: phase={s.phase!r}, expected 3")
    assert not wrong, "\n".join(wrong)


def test_file_stem_equals_frontmatter_name_for_all_phase3() -> None:
    """AC5: file stem == frontmatter name for all Phase-3 (three-way match).

    load_specialist enforces stem==name; this proves all 9 files pass the check.
    """
    reg = load_registry(_AGENTS)
    mismatches = []
    for name in _ALL_PHASE3_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            mismatches.append(f"{name!r}: not in registry")
            continue
        if s.frontmatter.name != name:
            mismatches.append(f"{name!r}: frontmatter.name={s.frontmatter.name!r} != registry key")
    assert not mismatches, "\n".join(mismatches)


# ---------------------------------------------------------------------------
# Boundary-line invariant: phase1_compound_prompt_builder (used by
# _task_pipeline.py) REJECTS bodies containing BOUNDARY_LINE — the builder
# injects it between <INSTRUCTIONS> and user input automatically.
# ---------------------------------------------------------------------------


def test_no_phase3_body_contains_boundary_line() -> None:
    """AC7: no Phase-3 body contains BOUNDARY_LINE (builder injects it at dispatch)."""
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE3_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            violations.append(f"{name!r}: not in registry — author or register it first")
            continue
        if BOUNDARY_LINE in s.body:
            violations.append(f"{name!r}: body contains BOUNDARY_LINE — builder will reject")
    assert not violations, "Phase-3 bodies illegally contain BOUNDARY_LINE:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# No placeholder markers — fail RED until stub bodies are enriched.
# ---------------------------------------------------------------------------


def test_no_phase3_body_contains_placeholder_marker() -> None:
    """AC1/AC2: no Phase-3 body or description retains placeholder text."""
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE3_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            continue  # Registry absence caught by positive-receipt tests above
        desc = s.frontmatter.description
        body = s.body
        for marker in _PLACEHOLDER_MARKERS:
            if marker.lower() in body.lower() or marker.lower() in desc.lower():
                violations.append(f"{name!r}: contains placeholder marker {marker!r}")
                break
    assert not violations, "Phase-3 specialists still contain placeholder content:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# JSON output contract checks — pipeline parsers require exact field names.
# ---------------------------------------------------------------------------


def test_test_author_declares_red_contract() -> None:
    """AC1/AC7: test-author body declares the RED-phase contract.

    _task_pipeline.py:179 requires tests_status=='red' from test-author.
    """
    reg = load_registry(_AGENTS)
    try:
        s = reg.get("test-author")
    except SpecialistError:
        pytest.skip("test-author not yet authored")
    missing = [kw for kw in _TDD_RED_REQUIRED if kw not in s.body]
    assert not missing, (
        f"test-author body missing contract keywords {missing!r}. "
        "Body must document {files:[...], tests_status:'red'}."
    )


def test_code_author_declares_green_contract() -> None:
    """AC1/AC7: code-author body declares the GREEN-phase contract.

    _task_pipeline.py:187 requires tests_status=='green' from code-author.
    """
    reg = load_registry(_AGENTS)
    try:
        s = reg.get("code-author")
    except SpecialistError:
        pytest.skip("code-author not yet authored")
    missing = [kw for kw in _TDD_GREEN_REQUIRED if kw not in s.body]
    assert not missing, (
        f"code-author body missing contract keywords {missing!r}. "
        "Body must document {files:[...], tests_status:'green'}."
    )


def test_code_reviewer_declares_verdict_contract() -> None:
    """AC1/AC7: code-reviewer body declares the verdict contract.

    _task_pipeline.py:255 uses parse_review_result expecting {verdict, notes}.
    """
    reg = load_registry(_AGENTS)
    try:
        s = reg.get("code-reviewer")
    except SpecialistError:
        pytest.skip("code-reviewer not yet authored")
    missing = [kw for kw in _REVIEW_REQUIRED if kw not in s.body]
    assert not missing, (
        f"code-reviewer body missing contract keywords {missing!r}. "
        "Body must document {verdict:'approved'|'rejected', notes:'...'}."
    )


# ---------------------------------------------------------------------------
# AC10: _task_pipeline.py is frozen — stage maps must not change.
# ---------------------------------------------------------------------------


def test_pipeline_stage_specialist_map_unchanged() -> None:
    """AC10: _STAGE_SPECIALIST has exactly the 3 frozen dispatched specialists."""
    from sdlc.cli._task_pipeline import _STAGE_SPECIALIST

    dispatched = {v for v in _STAGE_SPECIALIST.values() if v is not None}
    assert dispatched == _PIPELINE_DISPATCHED, (
        f"_STAGE_SPECIALIST changed: got {sorted(dispatched)!r}, "
        f"expected {sorted(_PIPELINE_DISPATCHED)!r}. Do NOT modify _task_pipeline.py."
    )
    for name in _POST_PIPELINE:
        assert name not in dispatched, (
            f"{name!r} must NOT be in _STAGE_SPECIALIST (post-pipeline delivery specialist)."
        )


def test_pipeline_next_stage_map_unchanged() -> None:
    """AC10: _NEXT_STAGE has exactly the frozen 4-entry map."""
    from sdlc.cli._task_pipeline import _NEXT_STAGE

    expected = {
        "pending": "write-tests",
        "write-tests": "write-code",
        "write-code": "review",
        "review": "done",
    }
    assert dict(_NEXT_STAGE) == expected, (
        f"_NEXT_STAGE changed: got {dict(_NEXT_STAGE)!r}. "
        "Do NOT modify _task_pipeline.py — frozen at 2A.17 done."
    )


# ---------------------------------------------------------------------------
# AC8: tool-safety posture — all Phase-3 specialists must declare tools: [].
# ---------------------------------------------------------------------------


def test_all_phase3_declare_empty_tools() -> None:
    """AC8: every Phase-3 specialist declares tools:[] (no network/Bash tools)."""
    reg = load_registry(_AGENTS)
    violations = []
    for name in _ALL_PHASE3_NAMES:
        try:
            s = reg.get(name)
        except SpecialistError:
            continue
        if s.frontmatter.tools:
            violations.append(f"{name!r}: tools={s.frontmatter.tools!r}, expected []")
    assert not violations, "\n".join(violations)


# ---------------------------------------------------------------------------
# AC9: Phase-3 conformance representative (D3=(a): code-author).
# ---------------------------------------------------------------------------


def test_code_author_is_phase3_conformance_representative() -> None:
    """AC9/D3=(a): code-author is registered as the Phase-3 conformance representative."""
    reg = load_registry(_AGENTS)
    try:
        s = reg.get("code-author")
    except SpecialistError:
        pytest.fail("code-author (Phase-3 conformance rep) not in registry.")
    assert s.phase == 3
    assert s.frontmatter.schema_version == 1
    assert s.frontmatter.name == "code-author"


# ---------------------------------------------------------------------------
# Negative receipts — prove the validator gate CAN fail (ADR-026 §1).
# These pass from the start; they are anti-tautology guards.
# ---------------------------------------------------------------------------


def test_malformed_specialist_icon_too_long_rejected() -> None:
    """Negative receipt: icon >4 chars raises SpecialistError (max_length=4 is load-bearing)."""
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "icon-too-long.md")


def test_malformed_specialist_missing_description_rejected() -> None:
    """Negative receipt: absent description raises SpecialistError (required field is enforced)."""
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "missing-description.md")

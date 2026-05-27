"""Prompt-injection corpus regression (Story 2B.4, NFR-SEC-3 / NFR-SEC-7).

Auto-discovers ``tests/security/corpus/user_text/*.txt`` and
``tests/security/corpus/workflow_yaml/*.yaml``.

Template census for *new* prompt builders is Story 2B.5
(``tests/security/test_boundary_line_presence.py``); this module deliberately
scopes to :func:`phase1_prompt_builder` for ``/sdlc-start`` (single primary
input). The :func:`phase1_compound_prompt_builder` (multi-input variants) is
part of the 2B.5 template-census surface — keep both stories cross-referenced
when adding builders or templates (AC3/D1; 2B.4 review D7-Recommended-c).

Helpers (parsers, fixtures, assertions, taxonomy constants) are extracted into
``tests/security/_corpus_helpers.py`` so this module stays within the
Architecture §765 / NFR-MAINT-3 LOC cap.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from sdlc.dispatcher import prompts as dispatcher_prompts
from sdlc.dispatcher.prompts import BOUNDARY_LINE, phase1_prompt_builder
from sdlc.errors import WorkflowError
from sdlc.workflows import load_workflow, sec7_heuristics, static_check
from sdlc.workflows import loader as workflow_loader
from sdlc.workflows.static_check import validate_workflow
from security._corpus_helpers import (
    ALL_CATEGORIES,
    ALL_REJECTORS,
    CORPUS_ROOT,
    DISPOSITION_REJECTED,
    REJECTION_REASON_PATTERNS,
    REQUIRED_CATEGORIES,
    REQUIRED_VECTORS,
    USER_IDEA_CLOSE_TAG,
    USER_IDEA_OPEN_TAG,
    USER_TEXT_DIR,
    VECTOR_INSTRUCTION_SHAPE,
    WORKFLOW_DIR,
    assert_boundary_before_user_idea,
    assert_workflow_loader_rejects,
    assert_workflow_rejected_per_metadata,
    build_start_prompt,
    discover_user_text_paths,
    discover_workflow_paths,
    load_user_text_case,
    load_workflow_case,
)

# --- pytest collection -------------------------------------------------------


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    # P15: parametrize IDs use ``p.name`` (preserves extension + case).
    # P16: eager metadata validation at collection time for fast-fail.
    if "user_corpus_path" in metafunc.fixturenames:
        paths = discover_user_text_paths()
        if not paths:
            pytest.fail(f"no user-text corpus under {USER_TEXT_DIR}")
        for p in paths:
            load_user_text_case(p)
        metafunc.parametrize(
            "user_corpus_path",
            paths,
            ids=[p.name for p in paths],
        )
    if "workflow_corpus_path" in metafunc.fixturenames:
        paths = discover_workflow_paths()
        if not paths:
            pytest.fail(f"no workflow corpus under {WORKFLOW_DIR}")
        for p in paths:
            load_workflow_case(p)
        metafunc.parametrize(
            "workflow_corpus_path",
            paths,
            ids=[p.name for p in paths],
        )


# --- minimum counts (P22) ----------------------------------------------------


@pytest.mark.integration
def test_user_text_corpus_minimum_count() -> None:
    """AC1: >=20 attack patterns."""
    paths = discover_user_text_paths()
    assert len(paths) >= 20, f"expected >=20 user-text patterns, got {len(paths)}"


@pytest.mark.integration
def test_workflow_yaml_corpus_minimum_count() -> None:
    """AC2: enforce both SEC-7 layer AND static_check layer floor (P22)."""
    paths = discover_workflow_paths()
    assert len(paths) >= 8, (
        f"expected >=8 workflow fixtures (>=4 sec7_* + >=4 static_*), got {len(paths)}"
    )
    sec7_n = sum(1 for p in paths if p.name.startswith("sec7_"))
    static_n = sum(1 for p in paths if p.name.startswith("static_"))
    assert sec7_n >= 4, f"need >=4 sec7_* fixtures (SEC-7 layer), got {sec7_n}"
    assert static_n >= 4, f"need >=4 static_* fixtures (static_check layer), got {static_n}"


# --- core regression tests --------------------------------------------------


@pytest.mark.integration
def test_user_text_corpus_disposition(user_corpus_path: Path) -> None:
    """AC3/D1: declared expected_disposition matches actual outcome.

    P7 — surface declared-vs-actual disposition diff on mismatch.
    D1-P — for rejected-at-validation, also assert the rejection reason.
    """
    meta, payload = load_user_text_case(user_corpus_path)
    disposition = meta["expected_disposition"]
    if disposition == DISPOSITION_REJECTED:
        expected_reason = meta["expected_reason"]
        reason_substring = REJECTION_REASON_PATTERNS[expected_reason]
        try:
            build_start_prompt(payload)
        except WorkflowError as exc:
            assert reason_substring in str(exc), (
                f"{user_corpus_path.name}: declared expected_reason="
                f"{expected_reason!r} (substring {reason_substring!r}) but "
                f"WorkflowError said: {exc!s}"
            )
            return
        pytest.fail(
            f"{user_corpus_path.name}: declared=rejected-at-validation "
            f"reason={expected_reason!r}, actual=boundary-wrapped "
            f"(prompt built without error)"
        )
    # disposition == boundary-wrapped
    try:
        prompt = build_start_prompt(payload)
    except WorkflowError as exc:
        pytest.fail(
            f"{user_corpus_path.name}: declared=boundary-wrapped, "
            f"actual=rejected-at-validation ({exc!s})"
        )
    assert_boundary_before_user_idea(prompt, payload)


@pytest.mark.integration
def test_workflow_yaml_corpus_rejected(workflow_corpus_path: Path) -> None:
    """AC2 + D2-P: each workflow YAML rejected at its declared layer."""
    assert_workflow_rejected_per_metadata(workflow_corpus_path)


# --- coverage assertions (P22, P23) -----------------------------------------


@pytest.mark.integration
def test_user_text_corpus_category_coverage() -> None:
    """AC1: every required category appears; no unknown categories present (P23)."""
    seen: set[str] = set()
    for path in discover_user_text_paths():
        meta, _ = load_user_text_case(path)
        seen.add(meta["category"])
    missing = REQUIRED_CATEGORIES - seen
    assert not missing, f"user-text corpus missing categories: {sorted(missing)}"
    unknown = seen - ALL_CATEGORIES
    assert not unknown, f"user-text corpus has unknown categories: {sorted(unknown)}"


@pytest.mark.integration
def test_workflow_yaml_corpus_vector_coverage() -> None:
    """AC2: all four PRD §354-355 vectors AND both rejection layers represented."""
    seen_vectors: set[str] = set()
    seen_rejectors: set[str] = set()
    for path in discover_workflow_paths():
        meta = load_workflow_case(path)
        seen_vectors.add(meta["expected_vector"])
        seen_rejectors.add(meta["expected_rejector"])
    missing_v = REQUIRED_VECTORS - seen_vectors
    assert not missing_v, f"workflow corpus missing vectors: {sorted(missing_v)}"
    missing_r = ALL_REJECTORS - seen_rejectors
    assert not missing_r, f"workflow corpus missing rejectors: {sorted(missing_r)}"


# --- structural / metadata invariants ---------------------------------------


@pytest.mark.integration
def test_corpus_documents_exercised_prompt_builders() -> None:
    """AC3/D1 (P1): builders this corpus exercises are callable AND 2B.5 cross-referenced."""
    assert callable(phase1_prompt_builder)
    readme_text = (CORPUS_ROOT / "README.md").read_text(encoding="utf-8")
    assert "2B.5" in readme_text, "README must cross-reference Story 2B.5"
    assert "test_boundary_line_presence.py" in readme_text, "README must name the 2B.5 harness file"
    module_doc = __doc__ or ""
    assert "2B.5" in module_doc and "test_boundary_line_presence.py" in module_doc, (
        "harness docstring must cross-reference Story 2B.5"
    )


@pytest.mark.integration
def test_envelope_tag_constants_match_production() -> None:
    """D3 (Recommended b) + P33: catch envelope-tag rename in production code.

    Reflective check: source of ``phase1_prompt_builder`` must contain
    ``<USER_IDEA>`` and ``</USER_IDEA>`` literals.
    """
    source = inspect.getsource(phase1_prompt_builder)
    assert USER_IDEA_OPEN_TAG in source, (
        f"production envelope-tag mismatch; "
        f"USER_IDEA_OPEN_TAG={USER_IDEA_OPEN_TAG!r} not in builder source"
    )
    assert USER_IDEA_CLOSE_TAG in source, (
        f"production envelope-tag mismatch; "
        f"USER_IDEA_CLOSE_TAG={USER_IDEA_CLOSE_TAG!r} not in builder source"
    )


@pytest.mark.integration
def test_boundary_smuggle_fixture_matches_constant() -> None:
    """P10: ``boundary_marker_smuggle_01.txt`` payload must equal ``BOUNDARY_LINE``.

    If the production constant ever drifts, this test fails loudly so the corpus
    is kept in sync (rather than the fixture silently desyncing).
    """
    path = USER_TEXT_DIR / "boundary_marker_smuggle_01.txt"
    _, payload = load_user_text_case(path)
    assert payload == BOUNDARY_LINE, (
        f"corpus fixture must equal production BOUNDARY_LINE constant; "
        f"fixture={payload!r} constant={BOUNDARY_LINE!r}"
    )


@pytest.mark.integration
def test_workflow_corpus_complements_existing_sec7_fixtures() -> None:
    """P8 + AC2: 2B.4 sec7_*.yaml content must NOT duplicate the existing SEC-7 set."""
    existing_dir = Path(__file__).parent.parent / "fixtures" / "workflows" / "adversarial" / "sec7"
    assert existing_dir.is_dir(), f"expected existing SEC-7 fixture dir {existing_dir}"
    existing_hashes = {
        hashlib.sha256(p.read_bytes()).hexdigest() for p in existing_dir.glob("*.yaml")
    }
    new_hashes = {
        hashlib.sha256(p.read_bytes()).hexdigest() for p in WORKFLOW_DIR.glob("sec7_*.yaml")
    }
    overlap = existing_hashes & new_hashes
    assert not overlap, (
        f"2B.4 sec7_* fixtures duplicate existing adversarial/sec7/ fixtures "
        f"(content hashes overlap): {sorted(overlap)}"
    )


# --- anti-tautology receipts (AC5; ADR-026 §1) ------------------------------


@pytest.mark.integration
def test_anti_tautology_boundary_line_is_load_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5 (P2): monkeypatch BOUNDARY_LINE in the production module.

    The freshly-built prompt must fail the assertion — proving the builder
    reads the constant (not a hand-rolled copy in the test).
    """
    benign_path = USER_TEXT_DIR / "benign_product_idea.txt"
    _, payload = load_user_text_case(benign_path)
    monkeypatch.setattr(dispatcher_prompts, "BOUNDARY_LINE", "XX-BOUNDARY-DISABLED-XX")
    prompt = build_start_prompt(payload)
    with pytest.raises(AssertionError, match="BOUNDARY_LINE must appear EXACTLY ONCE"):
        assert_boundary_before_user_idea(prompt, payload)


@pytest.mark.integration
def test_anti_tautology_boundary_ordering_is_enforced() -> None:
    """AC5 (P6): a prompt with BOUNDARY_LINE AFTER <USER_IDEA> fails the assertion."""
    bogus = (
        f"<SYSTEM>...</SYSTEM>\n<USER_IDEA>\nhello\n</USER_IDEA>\n"
        f"<BOUNDARY>\n{BOUNDARY_LINE}\n</BOUNDARY>\n"
    )
    with pytest.raises(AssertionError, match="BOUNDARY_LINE must appear EXACTLY ONCE"):
        assert_boundary_before_user_idea(bogus, "hello")


@pytest.mark.integration
def test_anti_tautology_sec7_heuristic_is_load_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5 (P4): SEC-7 instruction-shape rejection is load-bearing.

    Patch at BOTH ``sec7_heuristics`` source AND the loader-imported alias so
    future import-style refactors do not silently neuter the receipt.
    """
    fixture = WORKFLOW_DIR / "sec7_postcondition_instruction_override.yaml"
    assert_workflow_loader_rejects(fixture, vector=VECTOR_INSTRUCTION_SHAPE)

    def _noop(_field: str, _value: str) -> None:
        return None

    monkeypatch.setattr(sec7_heuristics, "check_instruction_shape_for_field", _noop)
    monkeypatch.setattr(workflow_loader, "check_instruction_shape_for_field", _noop)
    spec = load_workflow(fixture)
    assert "ignore" in spec.postconditions[0].lower()


@pytest.mark.integration
def test_anti_tautology_static_check_phantom_agent_is_load_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5 (P3 + P5): phantom-agent static-check is load-bearing.

    Today: assert phantom-agent error fires with structured ``details["agent"]``
    (not a substring match on the message — P5).
    Anti-tautology: monkeypatch ``_check_phantom_agents`` to no-op; validate
    must NOT raise the phantom-agent error.
    """
    fixture = WORKFLOW_DIR / "static_phantom_agent_write_globs.yaml"
    spec = load_workflow(fixture)
    with pytest.raises(WorkflowError) as exc_info:
        validate_workflow(spec)
    assert exc_info.value.details.get("agent") == "undeclared-red-team-agent", (
        f"expected phantom-agent details, got {exc_info.value.details!r}"
    )

    def _noop(_globs: object, _known_agents: object) -> None:
        return None

    monkeypatch.setattr(static_check, "_check_phantom_agents", _noop)
    try:
        validate_workflow(spec)
    except WorkflowError as exc:
        # Acceptable iff the error is NOT the phantom-agent rejection.
        assert "phantom-agent" not in str(exc).lower(), (
            f"phantom-agent check still firing after monkeypatch: {exc!s}"
        )

"""Property tests for disjoint-writes static checker (Story 2A.1, AC5).

Mandated file path: tests/property/test_disjoint_writes_static_check.py
(Architecture §995).

Invariant (post-P1 sound rewrite): the segment-aware overlap detector returns
``True`` iff at least one of the deterministic probe paths in
``_PROBE_PATHS`` is matched by both globs. The validator therefore:
- MUST raise when probes show overlap;
- MUST NOT raise when probes show NO overlap (false-negative would mean the
  validator is over-permissive; false-positive would mean it is over-strict
  beyond what the probes can witness).

This tightening (P2 from review of 2A.1) closes the previous "either outcome
acceptable in the no-overlap branch" loophole that allowed a degenerate
"always-raise" validator to pass the test vacuously.

hypothesis.settings: derandomize=True for byte-stable CI failures per D1
byte-stability work (commit 8498ac3, ADR-024 §"Property test determinism").
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.workflows.static_check import (
    _patterns_can_overlap,
    _segments,
    validate_workflow,
)

# Glob strategy per AC5 spec — extended (P2/edge) with degenerate cases that
# are valid YAML and exercise the validator's edges.
_GLOB_STRATEGY = st.sampled_from(
    [
        "*.json",
        "**/*.json",
        "01/*.json",
        "01/**",
        "01/02/*.json",
        "**/02/*.json",
        # Edge cases added in P2: degenerate but valid globs.
        "**",
        "*",
        "01/02/exact.json",
    ]
)

# Deterministic probe paths for property invariant assertion (AC5 spec).
# Designed to exercise the cross-product of segment-aware patterns above.
_PROBE_PATHS: tuple[str, ...] = (
    "a.json",
    "01/a.json",
    "01/02/a.json",
    "02/a.json",
    "01/02/b.json",
    "deep/01/02/c.json",
    "01/02/exact.json",
    "01/x.json",
    "anything",
)


def _make_two_agent_spec(g1: str, g2: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "schema_version": 1,
            "name": "prop-test",
            "slash_command": "/prop-test",
            "primary_agent": "agent-a",
            "parallel_agents": ["agent-b"],
            "write_globs": {
                "agent-a": [g1],
                "agent-b": [g2],
            },
            "stop_on_postcondition_failure": True,
        }
    )


def _segment_aware_match(pattern: str, path: str) -> bool:
    """Reference matcher: segment-aware (no fnmatch-across-slashes).

    Used by the property test as an oracle independent of the validator's
    implementation. Mirrors the algorithm in ``static_check._match_segments``.
    """
    p_segs = tuple(PurePosixPath(pattern).parts)
    path_segs = tuple(PurePosixPath(path).parts)
    return _ref_match(p_segs, path_segs)


def _ref_match(p_segs: tuple[str, ...], path_segs: tuple[str, ...]) -> bool:
    if not p_segs and not path_segs:
        return True
    if not p_segs:
        return False
    if p_segs[0] == "**":
        if _ref_match(p_segs[1:], path_segs):
            return True
        if not path_segs:
            return False
        return _ref_match(p_segs, path_segs[1:])
    if not path_segs:
        return False
    if not fnmatch.fnmatchcase(path_segs[0], p_segs[0]):
        return False
    return _ref_match(p_segs[1:], path_segs[1:])


def _probes_overlap(g1: str, g2: str) -> bool:
    """True if at least one probe path is matched by both globs (segment-aware)."""
    return any(_segment_aware_match(g1, p) and _segment_aware_match(g2, p) for p in _PROBE_PATHS)


@pytest.mark.property
@settings(max_examples=200, derandomize=True)
@given(g1=_GLOB_STRATEGY, g2=_GLOB_STRATEGY)
def test_disjoint_writes_invariant(g1: str, g2: str) -> None:
    """Two-direction invariant (P2 tightening of the previous "either outcome
    acceptable" loophole):

    1. **Soundness against false-negatives** — if the deterministic
       segment-aware probe oracle finds at least one overlap probe, the
       validator MUST raise. This catches a degenerate "always-pass" validator.
    2. **Soundness against false-positives** — if the validator raises, the
       ``witness`` recorded in ``details`` MUST actually be matched by both
       globs (segment-aware). This catches a degenerate "always-raise" validator
       (whose witness would not match) and any over-permissive overlap
       heuristic that returns a hallucinated path.
    """
    overlap = _probes_overlap(g1, g2)
    spec = _make_two_agent_spec(g1, g2)

    raised: WorkflowError | None = None
    try:
        validate_workflow(spec)
    except WorkflowError as exc:
        raised = exc

    if overlap:
        assert raised is not None, (
            f"probe oracle found overlap for ({g1!r}, {g2!r}) but validator "
            f"did not raise — false-negative."
        )
        assert "disjoint-writes violation" in str(raised)

    if raised is not None and raised.details.get("specialists"):
        witness = raised.details.get("witness")
        # Witness must be a concrete path that matches both globs (otherwise
        # the validator hallucinated an overlap).
        assert isinstance(witness, str) and witness, (
            f"validator raised but witness is missing or empty for "
            f"({g1!r}, {g2!r}); details={raised.details!r}"
        )
        assert _segment_aware_match(g1, witness), (
            f"witness {witness!r} does not match g1={g1!r} — false-positive."
        )
        assert _segment_aware_match(g2, witness), (
            f"witness {witness!r} does not match g2={g2!r} — false-positive."
        )


@pytest.mark.property
@settings(max_examples=200, derandomize=True)
@given(g1=_GLOB_STRATEGY, g2=_GLOB_STRATEGY)
def test_patterns_can_overlap_is_consistent_with_probes(g1: str, g2: str) -> None:
    """``_patterns_can_overlap`` agrees with the probe-based oracle.

    If the segment-aware oracle finds an overlap probe, the implementation
    MUST also detect overlap. (Implementation may detect more overlaps than
    the finite probe set — false-positive direction is acceptable.)
    """
    if _probes_overlap(g1, g2):
        assert _patterns_can_overlap(_segments(g1), _segments(g2)), (
            f"oracle found overlap probe for ({g1!r}, {g2!r}) but implementation "
            f"reports disjoint — implementation is unsound (false negative)."
        )

"""Unit tests for abstraction-adequacy helper primitives (Story 1.14, AC4).

Verifies determinism of the helpers in isolation so that the golden-file gate
in tests/integration/test_abstraction_adequacy.py is built on a trusted foundation.

If _SEED_PROMPT changes → test_seed_prompt_hash_is_byte_stable catches it.
If _canonicalize_state_for_hash drifts → test_canonical_state_hash_is_stable catches it.
If _synthesize_hook_payload is non-pure → test_synthesize_hook_payload_is_pure catches it.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Mapping

import pytest

from integration._abstraction_adequacy_helpers import (
    _SEED_PROMPT,
    _canonicalize_state_for_hash,
    _synthesize_hook_payload,
)
from sdlc.runtime import AgentResult
from sdlc.state.model import State

pytestmark = pytest.mark.unit


def _make_result(tool_calls: tuple[Mapping[str, object], ...] = ()) -> AgentResult:
    return AgentResult(
        output_text="test output",
        tool_calls=tool_calls,
        tokens_in=1,
        tokens_out=2,
    )


_ZERO_HASH = "sha256:" + "0" * 64


def _make_seed_result() -> AgentResult:
    return _make_result(
        tool_calls=(
            {
                "name": "write_artifact",
                "args": {
                    "target": "01-Requirement/04-Epics/EPIC-abstraction-adequacy.json",
                    "content_hash": _ZERO_HASH,
                },
            },
        )
    )


def test_seed_prompt_hash_is_byte_stable() -> None:
    # If _SEED_PROMPT is accidentally edited, regenerate goldens — see ADR-017.
    actual = "sha256:" + hashlib.sha256(_SEED_PROMPT.encode("utf-8")).hexdigest()
    expected = "sha256:1944573a27dc9cc1fb5fc366b4e6df342aa013515e5e686ecfc70c27d2b9b62d"
    assert actual == expected


def test_synthesize_hook_payload_is_pure() -> None:
    result = _make_seed_result()
    hp_a = _synthesize_hook_payload(result, seq=0)
    hp_b = _synthesize_hook_payload(result, seq=0)
    assert hp_a.model_dump(mode="json") == hp_b.model_dump(mode="json")


def test_synthesize_hook_payload_seq0_has_none_before_hash() -> None:
    result = _make_seed_result()
    hp = _synthesize_hook_payload(result, seq=0)
    assert hp.content_hash_before is None


def test_synthesize_hook_payload_seq1_has_content_hash_before() -> None:
    result = _make_seed_result()
    hp = _synthesize_hook_payload(result, seq=1)
    assert hp.content_hash_before == _ZERO_HASH


def test_canonical_state_hash_is_stable() -> None:
    state = State(schema_version=1, next_monotonic_seq=0, epics={"epic-1": {"k": "v"}})
    canonical = _canonicalize_state_for_hash(state)
    actual_hex = "sha256:" + hashlib.sha256(canonical).hexdigest()
    # If this assertion fails after a deliberate State model change, regenerate goldens.
    expected_hex = "sha256:cb698af12e10aa184fc84ec25c8ee1385d451e789664317890d30c6ae017d5fa"
    assert actual_hex == expected_hex


def test_synthesize_hook_payload_handles_missing_tool_calls() -> None:
    result = _make_result(tool_calls=())
    with pytest.raises(ValueError, match="exactly one tool_call"):
        _synthesize_hook_payload(result, seq=0)


def test_state_hash_is_deterministic_across_runs() -> None:
    """Subprocess determinism check: two separate python processes produce the same hash."""
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH — skip subprocess determinism test")

    script = (
        "import sys, json, hashlib; "
        "sys.path.insert(0, 'tests'); "
        "from integration._abstraction_adequacy_helpers import _state_hash; "
        "from sdlc.state.model import State; "
        "s = State(schema_version=1, next_monotonic_seq=0, epics={}); "
        "print(_state_hash(s))"
    )
    results = set()
    for _ in range(2):
        proc = subprocess.run(
            ["uv", "run", "python", "-c", script],
            capture_output=True,
            text=True,
            check=True,
        )
        results.add(proc.stdout.strip())
    assert len(results) == 1, f"non-deterministic hash across runs: {results}"

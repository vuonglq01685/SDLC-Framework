"""Unit tests for abstraction-adequacy helper primitives (Story 1.14, AC4).

Verifies determinism of the helpers in isolation so that the golden-file gate
in tests/integration/test_abstraction_adequacy.py is built on a trusted foundation.

If _SEED_PROMPT changes → test_seed_prompt_hash_is_byte_stable catches it.
If _canonicalize_state_for_hash drifts → test_canonical_state_hash_is_stable catches it.
If _hook_payload_from_agent_result is non-pure →
test_hook_payload_from_agent_result_is_pure catches it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from integration._abstraction_adequacy_helpers import (
    _SEED_PROMPT,
    _TARGET_ID,
    _canonicalize_state_for_hash,
    _hook_payload_from_agent_result,
    _state_hash,
    seed_fixture_has_extensibility_doc,
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


def test_hook_payload_from_agent_result_is_pure() -> None:
    result = _make_seed_result()
    hp_a = _hook_payload_from_agent_result(result, seq=0)
    hp_b = _hook_payload_from_agent_result(result, seq=0)
    assert hp_a.model_dump(mode="json") == hp_b.model_dump(mode="json")


def test_hook_payload_from_agent_result_seq0_has_none_before_hash() -> None:
    result = _make_seed_result()
    hp = _hook_payload_from_agent_result(result, seq=0)
    assert hp.content_hash_before is None


def test_hook_payload_from_agent_result_seq1_has_content_hash_before() -> None:
    result = _make_seed_result()
    hp = _hook_payload_from_agent_result(result, seq=1)
    assert hp.content_hash_before == _ZERO_HASH


def test_canonical_state_hash_is_stable() -> None:
    state = State(schema_version=1, next_monotonic_seq=0, epics={"epic-1": {"k": "v"}})
    canonical = _canonicalize_state_for_hash(state)
    actual_hex = "sha256:" + hashlib.sha256(canonical).hexdigest()
    # If this assertion fails after a deliberate State model change, regenerate goldens.
    # Story 1.15: State gained phase/stories/tasks fields (additive, schema_version unchanged).
    expected_hex = "sha256:6c7f5534fbb776fa67db12c8b688f558d0f845a15ca8eebcca1c9b92490a7714"
    assert actual_hex == expected_hex


def test_hook_payload_from_agent_result_uses_seed_target_when_tool_calls_empty() -> None:
    """ClaudeAIRuntime v1 leaves tool_calls empty — conformance uses seed-stable targets."""
    result = _make_result(tool_calls=())
    hp = _hook_payload_from_agent_result(result, seq=0)
    assert hp.target_path == "01-Requirement/04-Epics/EPIC-abstraction-adequacy.json"
    assert hp.content_hash_before is None


def test_hook_payload_from_agent_result_rejects_missing_args_target() -> None:
    """Typed validation: missing 'target' key surfaces a clear ValueError, not raw KeyError."""
    bad_result = _make_result(
        tool_calls=({"name": "write_artifact", "args": {"content_hash": _ZERO_HASH}},)
    )
    with pytest.raises(ValueError, match="tool_call shape mismatch"):
        _hook_payload_from_agent_result(bad_result, seq=0)


def test_hook_payload_from_agent_result_rejects_non_string_content_hash() -> None:
    """Typed validation: non-string content_hash surfaces a clear ValueError, not silent str()."""
    bad_result = _make_result(
        tool_calls=(
            {
                "name": "write_artifact",
                "args": {"target": "x", "content_hash": 0x1234},
            },
        )
    )
    with pytest.raises(ValueError, match=r"content_hash.* must be str"):
        _hook_payload_from_agent_result(bad_result, seq=1)


def test_seed_fixture_documents_extensibility_procedure() -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "mock_responses"
        / "abstraction-adequacy.yaml"
    )
    assert seed_fixture_has_extensibility_doc(fixture)


def test_state_hash_is_deterministic_within_process() -> None:
    """In-process determinism: repeat computation on equivalent States produces equal hashes.

    Replaces an earlier subprocess-based check that shelled out to `uv run python` (slow,
    no timeout, relative sys.path). The same coverage is achievable in-process: two
    independent State constructions of the same logical content must hash identically —
    catches non-determinism in `_canonicalize_state_for_hash` or `_state_hash`.
    """
    state_a = State(schema_version=1, next_monotonic_seq=0, epics={})
    state_b = State(schema_version=1, next_monotonic_seq=0, epics={})
    hash_a = _state_hash(state_a)
    hash_b = _state_hash(state_b)
    assert hash_a == hash_b
    assert hash_a.startswith("sha256:")
    assert len(hash_a) == len("sha256:") + 64


def test_target_id_matches_projection_epic_pattern() -> None:
    """Pin: _TARGET_ID must match state.projection._EPIC_ID_PATTERN.

    If not, project_from_journal silently drops the epic-mutation branch and the
    integration goldens validate only next_monotonic_seq advancement — a CRITICAL
    coverage gap on the abstraction-adequacy gate.

    Pattern is mirrored locally (rather than imported) so a future relax in projection
    fails this assertion deliberately rather than silently widening _TARGET_ID's
    apparent match surface.
    """
    pattern = re.compile(r"\Aepic-[0-9]+\Z")  # mirror of state.projection._EPIC_ID_PATTERN
    assert pattern.fullmatch(_TARGET_ID), (
        f"_TARGET_ID={_TARGET_ID!r} must match epic-N pattern; "
        "otherwise the projection bypasses the epic-mutation branch"
    )


def test_regenerate_goldens_flag_is_false() -> None:
    """Cross-platform guard: catches an accidentally-committed _REGENERATE_GOLDENS = True.

    Runs on Windows AND POSIX (the integration test is skipif-Windows; this guard is not).
    A leaked True flag would silently overwrite goldens on the next POSIX CI run.
    """
    # Imported here, not at module top, so this file does not couple to the integration
    # test module's import order during pytest collection.
    from integration.test_abstraction_adequacy import _REGENERATE_GOLDENS

    assert _REGENERATE_GOLDENS is False, (
        "_REGENERATE_GOLDENS = True must NEVER be committed — the goldens would be "
        "silently overwritten on the next POSIX run"
    )

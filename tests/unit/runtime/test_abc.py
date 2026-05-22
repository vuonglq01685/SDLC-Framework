from __future__ import annotations

import json
from collections.abc import Mapping

import pydantic
import pytest

from sdlc.runtime import AgentResult, AIRuntime


@pytest.mark.unit
def test_airuntime_is_abc_with_only_dispatch_abstract() -> None:
    assert AIRuntime.__abstractmethods__ == frozenset({"dispatch"})


@pytest.mark.unit
def test_airuntime_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        AIRuntime()  # type: ignore[abstract]


@pytest.mark.unit
def test_airuntime_subclass_must_implement_dispatch() -> None:
    class _Incomplete(AIRuntime):
        pass

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


@pytest.mark.unit
def test_airuntime_subclass_with_dispatch_instantiates() -> None:
    class _Concrete(AIRuntime):
        async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult:
            return AgentResult(output_text="ok", tool_calls=(), tokens_in=0, tokens_out=0)

    _Concrete()  # no error


@pytest.mark.unit
def test_airuntime_has_no_streaming_methods() -> None:
    members = dir(AIRuntime)
    for name in members:
        assert "stream" not in name, f"Forbidden streaming method found: {name}"
        assert "astream" not in name, f"Forbidden streaming method found: {name}"
        assert "iter_dispatch" not in name, f"Forbidden streaming method found: {name}"


@pytest.mark.unit
def test_agent_result_is_frozen() -> None:
    r = AgentResult(output_text="x", tool_calls=(), tokens_in=0, tokens_out=0)
    with pytest.raises((pydantic.ValidationError, TypeError, AttributeError)):
        r.output_text = "y"  # type: ignore[misc]


@pytest.mark.unit
def test_agent_result_extra_field_forbidden() -> None:
    with pytest.raises(pydantic.ValidationError):
        AgentResult(
            output_text="x",
            tool_calls=(),
            tokens_in=0,
            tokens_out=0,
            extra_field="nope",  # type: ignore[call-arg]
        )


@pytest.mark.unit
def test_agent_result_negative_token_counts_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        AgentResult(output_text="x", tool_calls=(), tokens_in=-1, tokens_out=0)


@pytest.mark.unit
def test_agent_result_canonical_serialization_is_byte_stable() -> None:
    r = AgentResult(
        output_text="hello",
        tool_calls=({"name": "x", "args": {}},),
        tokens_in=10,
        tokens_out=20,
    )
    serialized = json.dumps(r.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    expected = json.dumps(
        {
            "mock": False,
            "output_text": "hello",
            "tool_calls": [{"name": "x", "args": {}}],
            "tokens_in": 10,
            "tokens_out": 20,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert serialized == expected

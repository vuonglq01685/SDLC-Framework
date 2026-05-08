from __future__ import annotations

import json
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from sdlc.contracts.workflow_spec import WorkflowSpec

_VALID_KWARGS: dict[str, object] = dict(
    name="sdlc-start",
    slash_command="/sdlc-start",
    primary_agent="orchestrator",
    write_globs={"orchestrator": ["**/*"]},
)

_GOLDEN = (
    b'{"name":"sdlc-start","parallel_agents":[],"postconditions":[],'
    b'"primary_agent":"orchestrator","schema_version":1,"slash_command":"/sdlc-start",'
    b'"stop_on_postcondition_failure":true,"synthesizer_agent":null,'
    b'"write_globs":{"orchestrator":["**/*"]}}'
)


def _canonicalize(obj: dict[str, object]) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@pytest.mark.unit
class TestWorkflowSpecHappyPath:
    def test_construct_with_required_fields(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        assert ws.name == "sdlc-start"
        assert ws.slash_command == "/sdlc-start"
        assert ws.primary_agent == "orchestrator"
        assert ws.write_globs == {"orchestrator": ("**/*",)}
        assert ws.parallel_agents == ()
        assert ws.synthesizer_agent is None
        assert ws.postconditions == ()
        assert ws.stop_on_postcondition_failure is True

    def test_default_schema_version(self) -> None:
        assert WorkflowSpec(**_VALID_KWARGS).schema_version == 1


@pytest.mark.unit
class TestWorkflowSpecSchemaVersionRejection:
    def test_schema_version_2_raises(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(schema_version=2, **_VALID_KWARGS)

    def test_schema_version_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(schema_version=0, **_VALID_KWARGS)

    def test_schema_version_true_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(schema_version=True, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_float_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(schema_version=1.0, **_VALID_KWARGS)  # type: ignore[arg-type]


_REQUIRED_FIELDS = ["name", "slash_command", "primary_agent", "write_globs"]


@pytest.mark.unit
class TestWorkflowSpecRequiredFields:
    def test_required_fields_list_is_exhaustive(self) -> None:
        actual = {n for n, f in WorkflowSpec.model_fields.items() if f.is_required()}
        assert set(_REQUIRED_FIELDS) == actual


@pytest.mark.unit
@pytest.mark.parametrize("missing_field", _REQUIRED_FIELDS)
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        WorkflowSpec(**kwargs)
    assert any(
        e["type"] == "missing" and missing_field in str(e["loc"]) for e in exc_info.value.errors()
    )


@pytest.mark.unit
class TestWorkflowSpecExtraField:
    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSpec(**_VALID_KWARGS, bogus_field="x")  # type: ignore[call-arg]
        assert any(
            e["type"] == "extra_forbidden" and e["loc"] == ("bogus_field",)
            for e in exc_info.value.errors()
        )


@pytest.mark.unit
class TestWorkflowSpecFieldConstraints:
    def test_stop_on_postcondition_failure_string_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(**{**_VALID_KWARGS, "stop_on_postcondition_failure": "yes"})

    def test_stop_on_postcondition_failure_int_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(
                **{**_VALID_KWARGS, "stop_on_postcondition_failure": 1}  # type: ignore[dict-item]
            )

    def test_wrong_type_parallel_agents_raises(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowSpec(**{**_VALID_KWARGS, "parallel_agents": "not-a-list"})


@pytest.mark.unit
class TestWorkflowSpecFrozenAndContainers:
    def test_attribute_reassignment_raises(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        with pytest.raises(ValidationError):
            ws.name = "other"  # type: ignore[misc]

    def test_write_globs_is_mappingproxy(self) -> None:
        assert isinstance(WorkflowSpec(**_VALID_KWARGS).write_globs, MappingProxyType)

    def test_write_globs_outer_mutation_raises(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        with pytest.raises(TypeError):
            ws.write_globs["new"] = ("y",)  # type: ignore[index]

    def test_write_globs_inner_is_tuple(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        assert isinstance(ws.write_globs["orchestrator"], tuple)

    def test_parallel_agents_inner_tuple(self) -> None:
        ws = WorkflowSpec(**{**_VALID_KWARGS, "parallel_agents": ["a", "b"]})
        assert isinstance(ws.parallel_agents, tuple)
        with pytest.raises(AttributeError):
            ws.parallel_agents.append("c")  # type: ignore[attr-defined]


@pytest.mark.unit
class TestWorkflowSpecWhitespacePreserved:
    def test_name_whitespace_not_stripped(self) -> None:
        ws = WorkflowSpec(**{**_VALID_KWARGS, "name": "  sdlc-start  "})
        assert ws.name == "  sdlc-start  "


@pytest.mark.unit
class TestWorkflowSpecEqualityAndHash:
    def test_equal_instances(self) -> None:
        assert WorkflowSpec(**_VALID_KWARGS) == WorkflowSpec(**_VALID_KWARGS)

    def test_unhashable_due_to_mappingproxy_write_globs(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        with pytest.raises(TypeError):
            hash(ws)


@pytest.mark.unit
class TestWorkflowSpecCanonical:
    def test_canonical_bytes_stable(self) -> None:
        assert _canonicalize(WorkflowSpec(**_VALID_KWARGS).model_dump(mode="json")) == _GOLDEN

    def test_canonical_bytes_stable_across_kwargs_order(self) -> None:
        ws1 = WorkflowSpec(**_VALID_KWARGS)
        kwargs_reversed = dict(reversed(list(_VALID_KWARGS.items())))
        ws2 = WorkflowSpec(**kwargs_reversed)
        assert _canonicalize(ws1.model_dump(mode="json")) == _canonicalize(
            ws2.model_dump(mode="json")
        )

    def test_canonical_bytes_unicode(self) -> None:
        ws = WorkflowSpec(**{**_VALID_KWARGS, "name": "sdlc-café"})
        canonical = _canonicalize(ws.model_dump(mode="json"))
        assert b"\xc3\xa9" in canonical

    def test_json_roundtrip(self) -> None:
        ws = WorkflowSpec(**_VALID_KWARGS)
        json_str = json.dumps(ws.model_dump(mode="json"))
        ws2 = WorkflowSpec(**json.loads(json_str))
        assert ws == ws2

from __future__ import annotations

import json
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from sdlc.contracts.resume_token import ResumeToken

_VALID_HASH = "sha256:" + "d" * 64

_VALID_KWARGS: dict[str, object] = dict(
    phase=1,
    cursor={},
    suggested_next_command="/sdlc-start",
    state_hash=_VALID_HASH,
)

_GOLDEN = (
    b'{"cursor":{},"phase":1,"schema_version":1,'
    b'"state_hash":"' + _VALID_HASH.encode() + b'",'
    b'"suggested_next_command":"/sdlc-start"}'
)


def _canonicalize(obj: dict[str, object]) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@pytest.mark.unit
class TestResumeTokenHappyPath:
    def test_construct_with_all_required_fields(self) -> None:
        rt = ResumeToken(**_VALID_KWARGS)
        assert rt.phase == 1
        assert rt.cursor == {}
        assert rt.suggested_next_command == "/sdlc-start"
        assert rt.state_hash == _VALID_HASH

    def test_default_schema_version(self) -> None:
        assert ResumeToken(**_VALID_KWARGS).schema_version == 1


@pytest.mark.unit
class TestResumeTokenSchemaVersionRejection:
    def test_schema_version_2_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(schema_version=2, **_VALID_KWARGS)

    def test_schema_version_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(schema_version=0, **_VALID_KWARGS)

    def test_schema_version_true_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(schema_version=True, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_float_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(schema_version=1.0, **_VALID_KWARGS)  # type: ignore[arg-type]


_REQUIRED_FIELDS = ["phase", "suggested_next_command", "state_hash"]


@pytest.mark.unit
class TestResumeTokenRequiredFields:
    def test_required_fields_list_is_exhaustive(self) -> None:
        actual = {n for n, f in ResumeToken.model_fields.items() if f.is_required()}
        assert set(_REQUIRED_FIELDS) == actual


@pytest.mark.unit
@pytest.mark.parametrize("missing_field", _REQUIRED_FIELDS)
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        ResumeToken(**kwargs)
    assert any(
        e["type"] == "missing" and missing_field in str(e["loc"]) for e in exc_info.value.errors()
    )


@pytest.mark.unit
class TestResumeTokenExtraField:
    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ResumeToken(**_VALID_KWARGS, bogus_field="x")  # type: ignore[call-arg]
        assert any(
            e["type"] == "extra_forbidden" and e["loc"] == ("bogus_field",)
            for e in exc_info.value.errors()
        )


@pytest.mark.unit
class TestResumeTokenFieldConstraints:
    def test_phase_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(**{**_VALID_KWARGS, "phase": -1})

    def test_state_hash_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(**{**_VALID_KWARGS, "state_hash": "sha256:def"})

    def test_state_hash_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(**{**_VALID_KWARGS, "state_hash": ""})

    def test_wrong_type_phase_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResumeToken(**{**_VALID_KWARGS, "phase": "not-an-int"})


@pytest.mark.unit
class TestResumeTokenFrozenAndContainers:
    def test_attribute_reassignment_raises(self) -> None:
        rt = ResumeToken(**_VALID_KWARGS)
        with pytest.raises(ValidationError):
            rt.phase = 2  # type: ignore[misc]

    def test_cursor_is_mappingproxy(self) -> None:
        assert isinstance(ResumeToken(**_VALID_KWARGS).cursor, MappingProxyType)

    def test_cursor_mutation_raises(self) -> None:
        rt = ResumeToken(**{**_VALID_KWARGS, "cursor": {"x": 1}})
        with pytest.raises(TypeError):
            rt.cursor["x"] = 999  # type: ignore[index]


@pytest.mark.unit
class TestResumeTokenWhitespacePreserved:
    def test_suggested_next_command_whitespace_not_stripped(self) -> None:
        rt = ResumeToken(**{**_VALID_KWARGS, "suggested_next_command": "  /sdlc-start  "})
        assert rt.suggested_next_command == "  /sdlc-start  "


@pytest.mark.unit
class TestResumeTokenEqualityAndHash:
    def test_equal_instances(self) -> None:
        assert ResumeToken(**_VALID_KWARGS) == ResumeToken(**_VALID_KWARGS)

    def test_unhashable_due_to_mappingproxy_cursor(self) -> None:
        rt = ResumeToken(**_VALID_KWARGS)
        with pytest.raises(TypeError):
            hash(rt)


@pytest.mark.unit
class TestResumeTokenCanonical:
    def test_canonical_bytes_stable(self) -> None:
        assert _canonicalize(ResumeToken(**_VALID_KWARGS).model_dump(mode="json")) == _GOLDEN

    def test_canonical_bytes_stable_across_kwargs_order(self) -> None:
        rt1 = ResumeToken(**_VALID_KWARGS)
        kwargs_reversed = dict(reversed(list(_VALID_KWARGS.items())))
        rt2 = ResumeToken(**kwargs_reversed)
        assert _canonicalize(rt1.model_dump(mode="json")) == _canonicalize(
            rt2.model_dump(mode="json")
        )

    def test_canonical_bytes_unicode(self) -> None:
        rt = ResumeToken(**{**_VALID_KWARGS, "suggested_next_command": "/sdlc-café"})
        canonical = _canonicalize(rt.model_dump(mode="json"))
        assert b"\xc3\xa9" in canonical

    def test_cursor_accepts_arbitrary_nested_keys(self) -> None:
        """Decision F3: open-ended cursor locks 'extra=forbid' at the top level only,
        NOT inside cursor. Mirror of test_payload_accepts_arbitrary_nested_keys (Story 1.21)."""
        rt = ResumeToken(
            **{
                **_VALID_KWARGS,
                "cursor": {"any": {"deeply": {"nested": ["array", 1, None, True]}}},
            }
        )
        assert rt.cursor["any"]["deeply"]["nested"] == ["array", 1, None, True]  # type: ignore[index]

    def test_json_roundtrip(self) -> None:
        rt = ResumeToken(**_VALID_KWARGS)
        json_str = json.dumps(rt.model_dump(mode="json"))
        rt2 = ResumeToken(**json.loads(json_str))
        assert rt == rt2

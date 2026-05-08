from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from sdlc.contracts.hook_payload import HookPayload

_VALID_HASH = "sha256:" + "c" * 64

_VALID_KWARGS: dict[str, object] = dict(
    hook_name="phase_gate",
    target_path="04-Epics/EPIC-x.json",
    target_kind="epic",
    content_hash_before=None,
    write_intent="create",
)

_GOLDEN = (
    b'{"content_hash_before":null,"hook_name":"phase_gate","schema_version":1,'
    b'"target_kind":"epic","target_path":"04-Epics/EPIC-x.json","write_intent":"create"}'
)


def _canonicalize(obj: dict[str, object]) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@pytest.mark.unit
class TestHookPayloadHappyPath:
    def test_construct_with_all_required_fields(self) -> None:
        hp = HookPayload(**_VALID_KWARGS)
        assert hp.hook_name == "phase_gate"
        assert hp.target_path == "04-Epics/EPIC-x.json"
        assert hp.target_kind == "epic"
        assert hp.content_hash_before is None
        assert hp.write_intent == "create"

    def test_default_schema_version(self) -> None:
        assert HookPayload(**_VALID_KWARGS).schema_version == 1

    def test_content_hash_before_can_be_valid_sha256(self) -> None:
        hp = HookPayload(**{**_VALID_KWARGS, "content_hash_before": _VALID_HASH})
        assert hp.content_hash_before == _VALID_HASH


@pytest.mark.unit
class TestHookPayloadSchemaVersionRejection:
    def test_schema_version_2_raises(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(schema_version=2, **_VALID_KWARGS)

    def test_schema_version_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(schema_version=0, **_VALID_KWARGS)

    def test_schema_version_true_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(schema_version=True, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_float_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(schema_version=1.0, **_VALID_KWARGS)  # type: ignore[arg-type]


_REQUIRED_FIELDS = [
    "hook_name",
    "target_path",
    "target_kind",
    "content_hash_before",
    "write_intent",
]


@pytest.mark.unit
class TestHookPayloadRequiredFields:
    def test_required_fields_list_is_exhaustive(self) -> None:
        actual = {n for n, f in HookPayload.model_fields.items() if f.is_required()}
        assert set(_REQUIRED_FIELDS) == actual


@pytest.mark.unit
@pytest.mark.parametrize("missing_field", _REQUIRED_FIELDS)
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        HookPayload(**kwargs)
    assert any(
        e["type"] == "missing" and missing_field in str(e["loc"]) for e in exc_info.value.errors()
    )


@pytest.mark.unit
class TestHookPayloadExtraField:
    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            HookPayload(**_VALID_KWARGS, bogus_field="x")  # type: ignore[call-arg]
        assert any(
            e["type"] == "extra_forbidden" and e["loc"] == ("bogus_field",)
            for e in exc_info.value.errors()
        )


@pytest.mark.unit
class TestHookPayloadFieldConstraints:
    def test_content_hash_before_invalid_format_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(**{**_VALID_KWARGS, "content_hash_before": "not-a-hash"})

    def test_content_hash_before_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(**{**_VALID_KWARGS, "content_hash_before": "sha256:abc"})

    def test_content_hash_before_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(**{**_VALID_KWARGS, "content_hash_before": ""})

    def test_wrong_type_hook_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            HookPayload(**{**_VALID_KWARGS, "hook_name": 123})


@pytest.mark.unit
class TestHookPayloadFrozen:
    def test_attribute_reassignment_raises(self) -> None:
        hp = HookPayload(**_VALID_KWARGS)
        with pytest.raises(ValidationError):
            hp.hook_name = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestHookPayloadWhitespacePreserved:
    def test_target_path_whitespace_not_stripped(self) -> None:
        hp = HookPayload(**{**_VALID_KWARGS, "target_path": "  /tmp/foo.txt  "})
        assert hp.target_path == "  /tmp/foo.txt  "


@pytest.mark.unit
class TestHookPayloadEqualityAndHash:
    def test_equal_instances(self) -> None:
        assert HookPayload(**_VALID_KWARGS) == HookPayload(**_VALID_KWARGS)

    def test_hashable(self) -> None:
        hp = HookPayload(**_VALID_KWARGS)
        assert isinstance(hash(hp), int)


@pytest.mark.unit
class TestHookPayloadCanonical:
    def test_canonical_bytes_stable(self) -> None:
        assert _canonicalize(HookPayload(**_VALID_KWARGS).model_dump(mode="json")) == _GOLDEN

    def test_canonical_bytes_stable_across_kwargs_order(self) -> None:
        hp1 = HookPayload(**_VALID_KWARGS)
        kwargs_reversed = dict(reversed(list(_VALID_KWARGS.items())))
        hp2 = HookPayload(**kwargs_reversed)
        assert _canonicalize(hp1.model_dump(mode="json")) == _canonicalize(
            hp2.model_dump(mode="json")
        )

    def test_canonical_bytes_unicode(self) -> None:
        hp = HookPayload(**{**_VALID_KWARGS, "target_path": "04-Epics/café.json"})
        canonical = _canonicalize(hp.model_dump(mode="json"))
        assert b"\xc3\xa9" in canonical

    def test_json_roundtrip(self) -> None:
        hp = HookPayload(**_VALID_KWARGS)
        json_str = json.dumps(hp.model_dump(mode="json"))
        hp2 = HookPayload(**json.loads(json_str))
        assert hp == hp2

from __future__ import annotations

import json
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from sdlc.contracts.journal_entry import JournalEntry

_VALID_AFTER = "sha256:" + "a" * 64
_VALID_BEFORE = "sha256:" + "b" * 64

_VALID_KWARGS: dict[str, object] = dict(
    monotonic_seq=1,
    ts="2026-05-08T09:42:13.487Z",
    actor="cli",
    kind="state_mutation",
    target_id="EPIC-x",
    before_hash=None,
    after_hash=_VALID_AFTER,
    payload={},
)

_GOLDEN = (
    b'{"actor":"cli","after_hash":"' + _VALID_AFTER.encode() + b'",'
    b'"before_hash":null,"kind":"state_mutation","monotonic_seq":1,"payload":{},'
    b'"schema_version":1,"target_id":"EPIC-x","ts":"2026-05-08T09:42:13.487Z"}'
)


def _canonicalize(obj: dict[str, object]) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@pytest.mark.unit
class TestJournalEntryHappyPath:
    def test_construct_with_all_required_fields(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        assert je.monotonic_seq == 1
        assert je.ts == "2026-05-08T09:42:13.487Z"
        assert je.actor == "cli"
        assert je.kind == "state_mutation"
        assert je.target_id == "EPIC-x"
        assert je.before_hash is None
        assert je.after_hash == _VALID_AFTER
        assert je.payload == {}

    def test_default_schema_version(self) -> None:
        assert JournalEntry(**_VALID_KWARGS).schema_version == 1

    def test_explicit_schema_version_1(self) -> None:
        je = JournalEntry(schema_version=1, **_VALID_KWARGS)
        assert je.schema_version == 1

    def test_before_hash_can_be_valid_sha256(self) -> None:
        je = JournalEntry(**{**_VALID_KWARGS, "before_hash": _VALID_BEFORE})
        assert je.before_hash == _VALID_BEFORE


@pytest.mark.unit
class TestJournalEntrySchemaVersionRejection:
    def test_schema_version_2_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            JournalEntry(schema_version=2, **_VALID_KWARGS)
        assert any(e["loc"] == ("schema_version",) for e in exc_info.value.errors())

    def test_schema_version_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(schema_version=0, **_VALID_KWARGS)

    def test_schema_version_true_rejected_strict(self) -> None:
        # bool would silently coerce to int 1 in lax mode; strict mode rejects it.
        with pytest.raises(ValidationError):
            JournalEntry(schema_version=True, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_float_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(schema_version=1.0, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_string_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(schema_version="1", **_VALID_KWARGS)  # type: ignore[arg-type]


_REQUIRED_FIELDS = [
    "monotonic_seq",
    "ts",
    "actor",
    "kind",
    "target_id",
    "before_hash",
    "after_hash",
]


@pytest.mark.unit
class TestJournalEntryRequiredFields:
    def test_required_fields_list_is_exhaustive(self) -> None:
        # Guard: if a new required field is added without updating _REQUIRED_FIELDS,
        # this assertion fails so the parametrized missing-field test stays exhaustive.
        actual = {n for n, f in JournalEntry.model_fields.items() if f.is_required()}
        assert set(_REQUIRED_FIELDS) == actual


@pytest.mark.unit
@pytest.mark.parametrize("missing_field", _REQUIRED_FIELDS)
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        JournalEntry(**kwargs)
    assert any(
        e["type"] == "missing" and missing_field in str(e["loc"]) for e in exc_info.value.errors()
    )


@pytest.mark.unit
class TestJournalEntryExtraField:
    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            JournalEntry(**_VALID_KWARGS, bogus_field="x")  # type: ignore[call-arg]
        assert any(
            e["type"] == "extra_forbidden" and e["loc"] == ("bogus_field",)
            for e in exc_info.value.errors()
        )


@pytest.mark.unit
class TestJournalEntryFieldConstraints:
    def test_monotonic_seq_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "monotonic_seq": -1})

    def test_ts_non_rfc3339_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "ts": "yesterday"})

    def test_ts_with_offset_not_z_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "ts": "2026-05-08T09:42:13+07:00"})

    def test_after_hash_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "after_hash": "sha256:abc"})

    def test_after_hash_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "after_hash": ""})

    def test_after_hash_wrong_algo_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "after_hash": "sha512:" + "a" * 64})

    def test_before_hash_invalid_format_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "before_hash": "not-a-hash"})

    def test_wrong_type_monotonic_seq_raises(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntry(**{**_VALID_KWARGS, "monotonic_seq": "not-an-int"})


@pytest.mark.unit
class TestJournalEntryFrozenAndContainers:
    def test_attribute_reassignment_raises(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        with pytest.raises(ValidationError):
            je.monotonic_seq = 2  # type: ignore[misc]

    def test_payload_is_mappingproxy(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        assert isinstance(je.payload, MappingProxyType)

    def test_payload_mutation_raises(self) -> None:
        je = JournalEntry(**{**_VALID_KWARGS, "payload": {"x": 1}})
        with pytest.raises(TypeError):
            je.payload["x"] = 999  # type: ignore[index]

    def test_payload_insertion_raises(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        with pytest.raises(TypeError):
            je.payload["new"] = "evil"  # type: ignore[index]


@pytest.mark.unit
class TestJournalEntryWhitespacePreserved:
    def test_actor_whitespace_not_stripped(self) -> None:
        # str_strip_whitespace=False is intentional for byte-stability;
        # this test locks-in the behavior so a future flip to True is caught.
        je = JournalEntry(**{**_VALID_KWARGS, "actor": "  cli  "})
        assert je.actor == "  cli  "


@pytest.mark.unit
class TestJournalEntryEqualityAndHash:
    def test_equal_instances(self) -> None:
        assert JournalEntry(**_VALID_KWARGS) == JournalEntry(**_VALID_KWARGS)

    def test_unhashable_due_to_mappingproxy_payload(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        with pytest.raises(TypeError):
            hash(je)


@pytest.mark.unit
class TestJournalEntryCanonical:
    def test_canonical_bytes_stable(self) -> None:
        je = JournalEntry(**_VALID_KWARGS)
        assert _canonicalize(je.model_dump(mode="json")) == _GOLDEN

    def test_canonical_bytes_stable_across_kwargs_order(self) -> None:
        # AC5 byte-stability: same logical instance built two ways must canonicalize identically.
        je1 = JournalEntry(**_VALID_KWARGS)
        kwargs_reversed = dict(reversed(list(_VALID_KWARGS.items())))
        je2 = JournalEntry(**kwargs_reversed)
        assert _canonicalize(je1.model_dump(mode="json")) == _canonicalize(
            je2.model_dump(mode="json")
        )

    def test_canonical_bytes_unicode(self) -> None:
        je = JournalEntry(**{**_VALID_KWARGS, "actor": "agent:café"})
        canonical = _canonicalize(je.model_dump(mode="json"))
        assert b"\xc3\xa9" in canonical

    def test_json_roundtrip(self) -> None:
        # Real wire-format invariant: dump-as-json → str → dict → reconstruct.
        je = JournalEntry(**_VALID_KWARGS)
        json_str = json.dumps(je.model_dump(mode="json"))
        je2 = JournalEntry(**json.loads(json_str))
        assert je == je2

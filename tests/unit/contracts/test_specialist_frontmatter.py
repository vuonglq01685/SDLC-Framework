from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter

_VALID_KWARGS: dict[str, object] = dict(
    name="requirement-analyst",
    title="Requirement Analyst",
    icon="\U0001f4dd",  # 📝
    model="opus",
    tools=(),
    read_globs=(),
    write_globs=(),
    description="Drafts PRDs",
)

_GOLDEN = (
    b'{"description":"Drafts PRDs","icon":"\xf0\x9f\x93\x9d","model":"opus",'
    b'"name":"requirement-analyst","read_globs":[],"schema_version":1,'
    b'"title":"Requirement Analyst","tools":[],"write_globs":[]}'
)


def _canonicalize(obj: dict[str, object]) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@pytest.mark.unit
class TestSpecialistFrontmatterHappyPath:
    def test_construct_with_all_required_fields(self) -> None:
        sf = SpecialistFrontmatter(**_VALID_KWARGS)
        assert sf.name == "requirement-analyst"
        assert sf.title == "Requirement Analyst"
        assert sf.icon == "\U0001f4dd"
        assert sf.model == "opus"
        assert sf.tools == ()
        assert sf.read_globs == ()
        assert sf.write_globs == ()
        assert sf.description == "Drafts PRDs"

    def test_default_schema_version(self) -> None:
        assert SpecialistFrontmatter(**_VALID_KWARGS).schema_version == 1

    def test_list_inputs_coerced_to_tuple(self) -> None:
        sf = SpecialistFrontmatter(**{**_VALID_KWARGS, "tools": ["edit", "read"]})
        assert isinstance(sf.tools, tuple)
        assert sf.tools == ("edit", "read")


@pytest.mark.unit
class TestSpecialistFrontmatterSchemaVersionRejection:
    def test_schema_version_2_raises(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(schema_version=2, **_VALID_KWARGS)

    def test_schema_version_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(schema_version=0, **_VALID_KWARGS)

    def test_schema_version_true_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(schema_version=True, **_VALID_KWARGS)  # type: ignore[arg-type]

    def test_schema_version_float_rejected_strict(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(schema_version=1.0, **_VALID_KWARGS)  # type: ignore[arg-type]


_REQUIRED_FIELDS = ["name", "title", "icon", "model", "description"]


@pytest.mark.unit
class TestSpecialistFrontmatterRequiredFields:
    def test_required_fields_list_is_exhaustive(self) -> None:
        actual = {n for n, f in SpecialistFrontmatter.model_fields.items() if f.is_required()}
        assert set(_REQUIRED_FIELDS) == actual


@pytest.mark.unit
@pytest.mark.parametrize("missing_field", _REQUIRED_FIELDS)
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = {k: v for k, v in _VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError) as exc_info:
        SpecialistFrontmatter(**kwargs)
    assert any(
        e["type"] == "missing" and missing_field in str(e["loc"]) for e in exc_info.value.errors()
    )


@pytest.mark.unit
class TestSpecialistFrontmatterExtraField:
    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SpecialistFrontmatter(**_VALID_KWARGS, bogus_field="x")  # type: ignore[call-arg]
        assert any(
            e["type"] == "extra_forbidden" and e["loc"] == ("bogus_field",)
            for e in exc_info.value.errors()
        )


@pytest.mark.unit
class TestSpecialistFrontmatterFieldConstraints:
    def test_icon_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(**{**_VALID_KWARGS, "icon": ""})

    def test_icon_too_long_rejected(self) -> None:
        # max_length=4; 5 chars must reject.
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(**{**_VALID_KWARGS, "icon": "hello"})

    def test_icon_compound_emoji_accepted(self) -> None:
        # ZWJ-joined family is up to 4 codepoints — must be accepted.
        sf = SpecialistFrontmatter(**{**_VALID_KWARGS, "icon": "👨‍💻"})
        assert sf.icon == "👨‍💻"

    def test_wrong_type_tools_raises(self) -> None:
        with pytest.raises(ValidationError):
            SpecialistFrontmatter(**{**_VALID_KWARGS, "tools": "not-a-list"})


@pytest.mark.unit
class TestSpecialistFrontmatterFrozenAndContainers:
    def test_attribute_reassignment_raises(self) -> None:
        sf = SpecialistFrontmatter(**_VALID_KWARGS)
        with pytest.raises(ValidationError):
            sf.name = "other"  # type: ignore[misc]

    def test_tools_is_tuple_immutable(self) -> None:
        sf = SpecialistFrontmatter(**{**_VALID_KWARGS, "tools": ["a", "b"]})
        # tuple has no mutating methods; this asserts type.
        assert isinstance(sf.tools, tuple)
        with pytest.raises(AttributeError):
            sf.tools.append("c")  # type: ignore[attr-defined]


@pytest.mark.unit
class TestSpecialistFrontmatterWhitespacePreserved:
    def test_title_whitespace_not_stripped(self) -> None:
        sf = SpecialistFrontmatter(**{**_VALID_KWARGS, "title": "  Analyst  "})
        assert sf.title == "  Analyst  "


@pytest.mark.unit
class TestSpecialistFrontmatterEqualityAndHash:
    def test_equal_instances(self) -> None:
        assert SpecialistFrontmatter(**_VALID_KWARGS) == SpecialistFrontmatter(**_VALID_KWARGS)

    def test_hashable_now_that_lists_are_tuples(self) -> None:
        # All fields are scalars or tuples → hashable in pydantic v2 frozen mode.
        sf = SpecialistFrontmatter(**_VALID_KWARGS)
        assert isinstance(hash(sf), int)


@pytest.mark.unit
class TestSpecialistFrontmatterCanonical:
    def test_canonical_bytes_stable(self) -> None:
        assert (
            _canonicalize(SpecialistFrontmatter(**_VALID_KWARGS).model_dump(mode="json")) == _GOLDEN
        )

    def test_canonical_bytes_stable_across_kwargs_order(self) -> None:
        sf1 = SpecialistFrontmatter(**_VALID_KWARGS)
        kwargs_reversed = dict(reversed(list(_VALID_KWARGS.items())))
        sf2 = SpecialistFrontmatter(**kwargs_reversed)
        assert _canonicalize(sf1.model_dump(mode="json")) == _canonicalize(
            sf2.model_dump(mode="json")
        )

    def test_canonical_bytes_contain_utf8_emoji(self) -> None:
        canonical = _canonicalize(SpecialistFrontmatter(**_VALID_KWARGS).model_dump(mode="json"))
        # 📝 is U+1F4DD → UTF-8: f0 9f 93 9d (not a \uXXXX escape)
        assert b"\xf0\x9f\x93\x9d" in canonical

    def test_json_roundtrip(self) -> None:
        sf = SpecialistFrontmatter(**_VALID_KWARGS)
        json_str = json.dumps(sf.model_dump(mode="json"))
        sf2 = SpecialistFrontmatter(**json.loads(json_str))
        assert sf == sf2

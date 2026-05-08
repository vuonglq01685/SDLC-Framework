from __future__ import annotations

import re

import pytest

from sdlc.config import REDACTION_MARKER, SECRET_PATTERNS, sanitize, sanitize_mapping

REDACTED = "<REDACTED:secret>"

# Representative secret literals for testing
SK_KEY = "sk-abc123def456ghi789jkl012mno345pq"
GHP_PAT = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
# JWT: three-segment base64url per RFC 7519
JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
STRIPE_LIVE = "pk_live_abc123def456ghi789jkl0"
STRIPE_TEST = "pk_test_abc123def456ghi789jkl0"


@pytest.mark.unit
class TestSanitize:
    def test_sk_key_redacted(self) -> None:
        result = sanitize(SK_KEY)
        assert result == REDACTED

    def test_sk_key_embedded(self) -> None:
        result = sanitize(f"Authorization: Bearer {SK_KEY}")
        assert REDACTED in result
        assert SK_KEY not in result

    def test_sk_key_prefix_position(self) -> None:
        result = sanitize(f"{SK_KEY} is the key")
        assert REDACTED in result

    def test_sk_key_suffix_position(self) -> None:
        result = sanitize(f"key is {SK_KEY}")
        assert REDACTED in result

    def test_ghp_pat_redacted(self) -> None:
        result = sanitize(GHP_PAT)
        assert result == REDACTED

    def test_stripe_live_redacted(self) -> None:
        result = sanitize(STRIPE_LIVE)
        assert result == REDACTED

    def test_stripe_test_redacted(self) -> None:
        result = sanitize(STRIPE_TEST)
        assert result == REDACTED

    def test_aws_access_key_redacted(self) -> None:
        result = sanitize(AWS_KEY)
        assert result == REDACTED

    def test_jwt_redacted(self) -> None:
        result = sanitize(JWT_TOKEN)
        assert result == REDACTED

    def test_multi_secret_string(self) -> None:
        text = f"token1={SK_KEY}; token2={GHP_PAT}"
        result = sanitize(text)
        assert SK_KEY not in result
        assert GHP_PAT not in result
        assert result.count(REDACTED) == 2

    def test_no_secret_passthrough(self) -> None:
        text = "just a normal string"
        assert sanitize(text) == text

    def test_empty_string_passthrough(self) -> None:
        assert sanitize("") == ""

    def test_idempotency(self) -> None:
        once = sanitize(SK_KEY)
        twice = sanitize(once)
        assert once == twice

    def test_idempotency_no_secret(self) -> None:
        text = "hello world"
        assert sanitize(sanitize(text)) == sanitize(text)


@pytest.mark.unit
class TestSanitizeMapping:
    def test_happy_path_nested(self) -> None:
        obj = {
            "path": "/tmp/x",
            "api_key": SK_KEY,
            "nested": {"token": GHP_PAT},
        }
        result = sanitize_mapping(obj)
        assert result["path"] == "/tmp/x"
        assert result["api_key"] == REDACTED
        assert result["nested"]["token"] == REDACTED  # type: ignore[index]

    def test_non_string_leaves_passthrough(self) -> None:
        obj = {
            "int_field": 42,
            "bool_field": True,
            "none_field": None,
            "float_field": 3.14,
            "str_field": SK_KEY,
        }
        result = sanitize_mapping(obj)
        assert result["int_field"] == 42
        assert result["bool_field"] is True
        assert result["none_field"] is None
        assert result["float_field"] == 3.14
        assert result["str_field"] == REDACTED

    def test_list_values_redacted(self) -> None:
        obj = {"tokens": [SK_KEY, "no-secret"]}
        result = sanitize_mapping(obj)
        tokens = result["tokens"]
        assert isinstance(tokens, list)
        assert tokens[0] == REDACTED
        assert tokens[1] == "no-secret"

    def test_immutability(self) -> None:
        original_key = SK_KEY
        obj = {"api_key": original_key}
        result = sanitize_mapping(obj)
        assert obj["api_key"] == original_key
        assert result["api_key"] == REDACTED
        assert result is not obj

    def test_secret_patterns_length(self) -> None:
        assert len(SECRET_PATTERNS) == 5
        for pattern in SECRET_PATTERNS:
            assert isinstance(pattern, re.Pattern)

    def test_redaction_marker_constant(self) -> None:
        assert REDACTION_MARKER == "<REDACTED:secret>"

    def test_empty_mapping(self) -> None:
        result = sanitize_mapping({})
        assert result == {}

    def test_all_five_patterns_in_single_mapping(self) -> None:
        obj = {
            "openai": SK_KEY,
            "github": GHP_PAT,
            "aws": AWS_KEY,
            "jwt": JWT_TOKEN,
            "stripe": STRIPE_LIVE,
        }
        result = sanitize_mapping(obj)
        for value in result.values():
            assert value == REDACTED, f"Expected REDACTED, got {value!r}"

    def test_tuple_values_recurse(self) -> None:
        obj = {"creds": (SK_KEY, "ok")}
        result = sanitize_mapping(obj)
        creds = result["creds"]
        assert isinstance(creds, tuple)
        assert creds == (REDACTED, "ok")

    def test_set_values_recurse(self) -> None:
        obj: dict[str, object] = {"tokens": {SK_KEY, "ok"}}
        result = sanitize_mapping(obj)
        tokens = result["tokens"]
        assert isinstance(tokens, set)
        assert tokens == {REDACTED, "ok"}

    def test_frozenset_values_recurse(self) -> None:
        obj: dict[str, object] = {"tokens": frozenset({SK_KEY, "ok"})}
        result = sanitize_mapping(obj)
        tokens = result["tokens"]
        assert isinstance(tokens, frozenset)
        assert tokens == frozenset({REDACTED, "ok"})

    def test_non_string_top_level_key_raises(self) -> None:
        obj: dict[object, object] = {123: "value"}
        with pytest.raises(TypeError, match="requires str keys"):
            sanitize_mapping(obj)  # type: ignore[arg-type]

    def test_non_string_nested_key_raises(self) -> None:
        obj: dict[str, object] = {"outer": {123: "value"}}
        with pytest.raises(TypeError, match="requires str keys"):
            sanitize_mapping(obj)

    def test_circular_dict_replaced_with_placeholder(self) -> None:
        obj: dict[str, object] = {"x": "ok"}
        obj["self"] = obj
        result = sanitize_mapping(obj)
        assert result["x"] == "ok"
        assert result["self"] == "<circular>"

    def test_circular_list_replaced_with_placeholder(self) -> None:
        inner: list[object] = ["ok"]
        inner.append(inner)
        obj: dict[str, object] = {"items": inner}
        result = sanitize_mapping(obj)
        items = result["items"]
        assert isinstance(items, list)
        assert items[0] == "ok"
        assert items[1] == "<circular>"

    def test_aws_key_word_boundary(self) -> None:
        # AKIA inside a longer alphanumeric run should NOT match (word-bounded).
        text = "PREFIXAKIAIOSFODNN7EXAMPLEXTRA"
        assert sanitize(text) == text  # bounded pattern leaves substring intact

    def test_aws_key_at_word_boundary_redacted(self) -> None:
        text = f"AWS_ACCESS_KEY_ID={AWS_KEY} done"
        result = sanitize(text)
        assert AWS_KEY not in result
        assert REDACTED in result

"""Task 1.2 — unit tests for _HookHashStore model (TDD-first, RED phase)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

# _HookHashStore is private; import from its actual home module (Story 2A.5
# DR1: tampering.py was split — model now lives in sdlc.hooks._hash_store).
from sdlc.hooks._hash_store import _HookHashStore

_VALID_HASH = "sha256:" + "a" * 64
_TS = "2026-05-10T12:00:00.000Z"

_VALID_DATA: dict[str, object] = {
    "schema_version": 1,
    "trusted_at": _TS,
    "hooks_root": ".claude/hooks",
    "hashes": {"hook_a.py": _VALID_HASH},
}


@pytest.mark.unit
class TestHookHashStoreHappyPath:
    def test_model_validate_happy_path(self) -> None:
        store = _HookHashStore.model_validate(_VALID_DATA)
        assert store.schema_version == 1
        assert store.trusted_at == _TS
        assert store.hooks_root == ".claude/hooks"
        assert store.hashes == {"hook_a.py": _VALID_HASH}

    def test_model_validate_empty_hashes(self) -> None:
        data = {**_VALID_DATA, "hashes": {}}
        store = _HookHashStore.model_validate(data)
        assert store.hashes == {}

    def test_model_dump_json_round_trip_byte_stable(self) -> None:
        store = _HookHashStore.model_validate(_VALID_DATA)
        dumped = store.model_dump_json()
        reloaded = _HookHashStore.model_validate_json(dumped)
        assert store == reloaded

    def test_frozen_instance_cannot_be_mutated(self) -> None:
        store = _HookHashStore.model_validate(_VALID_DATA)
        with pytest.raises((TypeError, ValidationError)):
            store.schema_version = 2  # type: ignore[assignment]


@pytest.mark.unit
class TestHookHashStoreRejects:
    def test_bad_schema_version_rejects(self) -> None:
        data = {**_VALID_DATA, "schema_version": 2}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_schema_version_zero_rejects(self) -> None:
        data = {**_VALID_DATA, "schema_version": 0}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_bad_hash_value_not_sha256_prefix_rejects(self) -> None:
        data = {**_VALID_DATA, "hashes": {"hook.py": "md5:abcdef"}}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_bad_hash_value_short_hex_rejects(self) -> None:
        data = {**_VALID_DATA, "hashes": {"hook.py": "sha256:abc"}}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_bad_trusted_at_format_rejects(self) -> None:
        data = {**_VALID_DATA, "trusted_at": "not-a-timestamp"}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_extra_field_forbidden(self) -> None:
        data = {**_VALID_DATA, "unexpected_field": "oops"}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_missing_required_field_rejects(self) -> None:
        data = {k: v for k, v in _VALID_DATA.items() if k != "trusted_at"}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)

    def test_strict_mode_rejects_float_schema_version(self) -> None:
        data = {**_VALID_DATA, "schema_version": 1.0}
        with pytest.raises(ValidationError):
            _HookHashStore.model_validate(data)


@pytest.mark.unit
class TestHookHashStoreRoundTrip:
    def test_model_dump_json_produces_canonical_sorted_keys(self) -> None:
        multi_hash: dict[str, object] = {
            **_VALID_DATA,
            "hashes": {
                "zz.py": "sha256:" + "f" * 64,
                "aa.py": "sha256:" + "0" * 64,
            },
        }
        store = _HookHashStore.model_validate(multi_hash)
        raw = json.loads(store.model_dump_json())
        hash_keys = list(raw["hashes"].keys())
        assert hash_keys == sorted(hash_keys)

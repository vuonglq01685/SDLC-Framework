"""Unit tests for the `adopted-symlinks.json` wire-format contract (Story 3.3, AC5).

`AdoptedSymlinks` is the 7th locked wire-format contract (ADR-024). These tests pin its
strict-mode behaviour (the immutability snapshot is enforced separately by
`tests/contracts/test_wireformat_immutability.py`).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping

pytestmark = pytest.mark.unit

_MAPPING = dict(
    source="docs/architecture-2024.md",
    target="02-Architecture/02-System/ARCHITECTURE.md",
    accepted_at="2026-06-04T09:42:13.487Z",
    kind="architecture",
)


def test_empty_manifest_defaults_to_no_mappings() -> None:
    manifest = AdoptedSymlinks()
    assert manifest.schema_version == 1
    assert manifest.mappings == ()


def test_round_trip_is_byte_stable() -> None:
    manifest = AdoptedSymlinks(mappings=(SymlinkMapping(**_MAPPING),))
    again = AdoptedSymlinks.model_validate_json(manifest.model_dump_json())
    assert again == manifest
    assert again.model_dump_json() == manifest.model_dump_json()


def test_mappings_accept_list_input_from_json_parser() -> None:
    # `mappings` is the StrictModel container opt-out (strict=False) — list → tuple.
    manifest = AdoptedSymlinks(mappings=[_MAPPING])
    assert isinstance(manifest.mappings, tuple)
    assert manifest.mappings[0].kind == "architecture"


def test_float_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        AdoptedSymlinks(schema_version=1.0)  # type: ignore[arg-type]
    assert any(e["loc"] == ("schema_version",) for e in exc.value.errors())


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AdoptedSymlinks(mappings=(), extra_field="nope")  # type: ignore[call-arg]


def test_mapping_rejects_non_rfc3339_accepted_at() -> None:
    bad = {**_MAPPING, "accepted_at": "2026-06-04 09:42:13"}
    with pytest.raises(ValidationError):
        SymlinkMapping(**bad)


def test_mapping_rejects_unknown_kind() -> None:
    bad = {**_MAPPING, "kind": "spreadsheet"}
    with pytest.raises(ValidationError):
        SymlinkMapping(**bad)  # type: ignore[arg-type]

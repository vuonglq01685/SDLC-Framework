"""Tests for specialists/manifest.py — _SpecialistManifest + _parse_manifest (AC1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import SpecialistError
from sdlc.specialists._manifest import _ManifestEntry, _parse_manifest, _SpecialistManifest

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "manifest"


@pytest.mark.unit
def test_parse_manifest_valid_minimal() -> None:
    manifest = _parse_manifest(_FIXTURES / "valid_minimal.yaml")
    assert manifest.schema_version == 1
    assert len(manifest.specialists) == 2
    names = {e.name for e in manifest.specialists}
    assert names == {"technical-researcher", "support-agent"}


@pytest.mark.unit
def test_parse_manifest_entry_fields() -> None:
    manifest = _parse_manifest(_FIXTURES / "valid_minimal.yaml")
    researcher = next(e for e in manifest.specialists if e.name == "technical-researcher")
    assert researcher.phase == 1
    assert researcher.file == "phase1/technical-researcher.md"


@pytest.mark.unit
def test_parse_manifest_entry_phase_zero_allowed() -> None:
    manifest = _parse_manifest(_FIXTURES / "valid_minimal.yaml")
    support = next(e for e in manifest.specialists if e.name == "support-agent")
    assert support.phase == 0


@pytest.mark.unit
def test_parse_manifest_unknown_top_level_key_raises() -> None:
    with pytest.raises(SpecialistError, match="unknown_top_level"):
        _parse_manifest(_FIXTURES / "unknown_key.yaml")


@pytest.mark.unit
def test_parse_manifest_bad_phase_raises() -> None:
    with pytest.raises(SpecialistError):
        _parse_manifest(_FIXTURES / "bad_phase.yaml")


@pytest.mark.unit
def test_parse_manifest_bad_name_raises() -> None:
    with pytest.raises(SpecialistError):
        _parse_manifest(_FIXTURES / "bad_name.yaml")


@pytest.mark.unit
def test_parse_manifest_missing_file_field_raises() -> None:
    with pytest.raises(SpecialistError):
        _parse_manifest(_FIXTURES / "missing_file.yaml")


@pytest.mark.unit
def test_parse_manifest_missing_manifest_file_raises() -> None:
    with pytest.raises(SpecialistError, match="not found"):
        _parse_manifest(_FIXTURES / "nonexistent.yaml")


@pytest.mark.unit
def test_manifest_entry_is_frozen() -> None:
    from pydantic import ValidationError

    entry = _ManifestEntry(name="foo-bar", phase=1, file="phase1/foo-bar.md")
    with pytest.raises(ValidationError):
        entry.name = "changed"  # pydantic frozen raises ValidationError at runtime


@pytest.mark.unit
def test_specialist_manifest_is_frozen() -> None:
    from pydantic import ValidationError

    manifest = _SpecialistManifest(schema_version=1, specialists=())
    with pytest.raises(ValidationError):
        manifest.schema_version = 2  # type: ignore[assignment]

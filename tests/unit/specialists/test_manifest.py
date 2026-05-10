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
    # P-R13: assert via SpecialistError.details["error"] (the wrapped pydantic
    # message) rather than via top-level match=, which is brittle to pydantic
    # error-rendering changes and could pass on any unrelated regression.
    with pytest.raises(SpecialistError) as exc_info:
        _parse_manifest(_FIXTURES / "unknown_key.yaml")
    assert "unknown_top_level" in exc_info.value.details["error"]


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


# ---------------------------------------------------------------------------
# P-R1 + P-R10: file path validation — defense-in-depth against traversal,
# absolute paths, and Windows-style backslashes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_manifest_rejects_path_traversal() -> None:
    with pytest.raises(SpecialistError, match=r"\.\."):
        _parse_manifest(_FIXTURES / "bad_path_traversal.yaml")


@pytest.mark.unit
def test_parse_manifest_rejects_absolute_path() -> None:
    with pytest.raises(SpecialistError, match="relative"):
        _parse_manifest(_FIXTURES / "bad_absolute_path.yaml")


@pytest.mark.unit
def test_parse_manifest_rejects_backslash_separator() -> None:
    with pytest.raises(SpecialistError, match="forward slashes"):
        _parse_manifest(_FIXTURES / "bad_backslash_path.yaml")


# ---------------------------------------------------------------------------
# P-R5: encoding errors wrapped as SpecialistError (PermissionError +
# UnicodeDecodeError must NOT bubble raw to callers)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_manifest_non_utf8_raises_specialist_error(tmp_path: Path) -> None:
    bad = tmp_path / "index.yaml"
    bad.write_bytes(b"\xff\xfe\x00schema_version: 1\n")  # invalid UTF-8 prefix
    with pytest.raises(SpecialistError, match="UTF-8"):
        _parse_manifest(bad)

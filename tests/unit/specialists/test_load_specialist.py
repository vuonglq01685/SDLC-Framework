"""Tests for specialists/_frontmatter.py — Specialist dataclass + load_specialist (AC2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.errors import SpecialistError
from sdlc.specialists import Specialist, load_specialist

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "markdown"


@pytest.mark.unit
def test_load_specialist_valid_minimal_returns_specialist() -> None:
    s = load_specialist(_FIXTURES / "valid-minimal.md")
    assert isinstance(s, Specialist)
    assert isinstance(s.frontmatter, SpecialistFrontmatter)


@pytest.mark.unit
def test_load_specialist_frontmatter_name_matches_stem() -> None:
    s = load_specialist(_FIXTURES / "valid-minimal.md")
    assert s.frontmatter.name == "valid-minimal"


@pytest.mark.unit
def test_load_specialist_body_preserved() -> None:
    s = load_specialist(_FIXTURES / "valid-minimal.md")
    assert "Valid Minimal Specialist" in s.body
    assert "This is the body" in s.body


@pytest.mark.unit
def test_load_specialist_source_path_is_absolute() -> None:
    path = _FIXTURES / "valid-minimal.md"
    s = load_specialist(path)
    assert s.source_path == path.resolve()
    assert s.source_path.is_absolute()


@pytest.mark.unit
def test_load_specialist_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    s = load_specialist(_FIXTURES / "valid-minimal.md")
    with pytest.raises(FrozenInstanceError):
        s.body = "changed"  # type: ignore[misc]


@pytest.mark.unit
def test_load_specialist_missing_frontmatter_delimiters_raises() -> None:
    with pytest.raises(SpecialistError, match="frontmatter"):
        load_specialist(_FIXTURES / "no-delim.md")


@pytest.mark.unit
def test_load_specialist_bad_yaml_raises() -> None:
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "bad-yaml.md")


@pytest.mark.unit
def test_load_specialist_frontmatter_validation_failure_raises() -> None:
    with pytest.raises(SpecialistError):
        load_specialist(_FIXTURES / "bad-frontmatter.md")


@pytest.mark.unit
def test_load_specialist_name_mismatch_raises() -> None:
    with pytest.raises(SpecialistError, match="name"):
        load_specialist(_FIXTURES / "name-mismatch.md")


@pytest.mark.unit
def test_load_specialist_io_error_raises() -> None:
    with pytest.raises(SpecialistError):
        load_specialist(Path("/nonexistent/path/missing.md"))


# ---------------------------------------------------------------------------
# P-R5: non-UTF-8 specialist files surface SpecialistError with a clear hint
# (UnicodeDecodeError is a ValueError subclass, NOT OSError — must be wrapped).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_specialist_non_utf8_raises_specialist_error(tmp_path: Path) -> None:
    bad = tmp_path / "non-utf8-specialist.md"
    bad.write_bytes(b"---\nname: non-utf8-specialist\nbad-byte: \xff\xfe\n---\nbody\n")
    with pytest.raises(SpecialistError, match="UTF-8"):
        load_specialist(bad)


# ---------------------------------------------------------------------------
# P-R25: standalone-loaded Specialist has phase=None (not 0); load_registry
# overrides with the manifest entry's int phase. Distinguishability test.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_specialist_standalone_has_phase_none() -> None:
    """A Specialist loaded outside a registry context carries phase=None."""
    s = load_specialist(_FIXTURES / "valid-minimal.md")
    assert s.phase is None

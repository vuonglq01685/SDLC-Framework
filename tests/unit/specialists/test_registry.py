"""Tests for specialists/_registry.py — SpecialistRegistry + load_registry (AC3, AC4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.errors import SpecialistError
from sdlc.specialists import SpecialistRegistry, load_registry

_REGISTRY_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "specialists" / "registry"
_VALID = _REGISTRY_FIXTURES / "valid_agents"
_ORPHAN = _REGISTRY_FIXTURES / "orphan_agents"
_MISSING_FILE = _REGISTRY_FIXTURES / "missing_file_agents"
_DUPLICATE = _REGISTRY_FIXTURES / "duplicate_agents"


# ---------------------------------------------------------------------------
# Happy-path: load_registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_registry_returns_specialist_registry() -> None:
    reg = load_registry(_VALID)
    assert isinstance(reg, SpecialistRegistry)


@pytest.mark.unit
def test_load_registry_loads_all_manifest_entries() -> None:
    reg = load_registry(_VALID)
    assert reg.names() == {"alpha-researcher", "beta-analyst", "gamma-support"}


@pytest.mark.unit
def test_load_registry_empty_manifest_ok() -> None:
    # src/sdlc/agents/ ships with empty manifest — must work.
    from pathlib import Path

    agents_dir = Path(__file__).resolve().parents[3] / "src" / "sdlc" / "agents"
    reg = load_registry(agents_dir)
    assert reg.names() == frozenset()


@pytest.mark.unit
def test_load_registry_missing_index_yaml_raises() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp, pytest.raises(SpecialistError, match="manifest"):
        load_registry(Path(tmp))


# ---------------------------------------------------------------------------
# AC3 enforcement: orphan and missing-file checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_registry_orphan_markdown_raises() -> None:
    with pytest.raises(SpecialistError, match="orphan"):
        load_registry(_ORPHAN)


@pytest.mark.unit
def test_load_registry_missing_manifest_file_raises() -> None:
    with pytest.raises(SpecialistError, match="missing"):
        load_registry(_MISSING_FILE)


@pytest.mark.unit
def test_load_registry_duplicate_name_in_manifest_raises() -> None:
    with pytest.raises(SpecialistError):
        load_registry(_DUPLICATE)


# ---------------------------------------------------------------------------
# AC4: SpecialistRegistry public surface — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_get_returns_specialist() -> None:
    from sdlc.specialists import Specialist

    reg = load_registry(_VALID)
    s = reg.get("alpha-researcher")
    assert isinstance(s, Specialist)
    assert s.frontmatter.name == "alpha-researcher"


@pytest.mark.unit
def test_registry_get_miss_raises() -> None:
    reg = load_registry(_VALID)
    with pytest.raises(SpecialistError, match="unknown specialist"):
        reg.get("nonexistent")


@pytest.mark.unit
def test_registry_list_phase_returns_matching() -> None:
    reg = load_registry(_VALID)
    phase1 = reg.list_phase(1)
    assert all(s.frontmatter.name == "alpha-researcher" for s in phase1)
    assert len(phase1) == 1


@pytest.mark.unit
def test_registry_list_phase_sorted_by_name() -> None:
    reg = load_registry(_VALID)
    all_phases = reg.list_phase(1) + reg.list_phase(2) + reg.list_phase(0)
    names = [s.frontmatter.name for s in all_phases]
    assert names == sorted(names)


@pytest.mark.unit
def test_registry_list_phase_empty_returns_empty_tuple() -> None:
    reg = load_registry(_VALID)
    assert reg.list_phase(3) == ()


@pytest.mark.unit
def test_registry_list_phase_invalid_phase_raises() -> None:
    reg = load_registry(_VALID)
    with pytest.raises(SpecialistError):
        reg.list_phase(5)


@pytest.mark.unit
def test_registry_list_returns_all_sorted() -> None:
    reg = load_registry(_VALID)
    all_s = reg.list()
    assert len(all_s) == 3
    names = [s.frontmatter.name for s in all_s]
    assert names == sorted(names)


@pytest.mark.unit
def test_registry_names_returns_frozenset() -> None:
    reg = load_registry(_VALID)
    names = reg.names()
    assert isinstance(names, frozenset)
    assert "alpha-researcher" in names


@pytest.mark.unit
def test_registry_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    reg = load_registry(_VALID)
    with pytest.raises(FrozenInstanceError):
        reg._specialists = {}  # type: ignore[misc,assignment]

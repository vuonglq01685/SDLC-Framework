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
def test_load_registry_empty_manifest_ok(tmp_path: Path) -> None:
    """Empty manifest (specialists: []) loads to an empty registry (P-R17).

    Uses tmp_path instead of the live src/sdlc/agents/ tree so the test is
    isolated from real specialist files that future stories will land.
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "index.yaml").write_text("schema_version: 1\nspecialists: []\n")
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
    # P-R16: anchor on the duplicate-name message so the test fails if a
    # future regression causes a different branch (e.g. missing-file) to fire
    # first while the duplicate-name check silently regresses.
    with pytest.raises(SpecialistError, match="duplicate specialist name"):
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
    # P-R19: assert non-empty FIRST so an `all()` over an empty tuple cannot
    # vacuously pass if a future regression causes the registry to lose the
    # matching specialist.
    reg = load_registry(_VALID)
    phase1 = reg.list_phase(1)
    assert len(phase1) == 1
    assert all(s.frontmatter.name == "alpha-researcher" for s in phase1)


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


# ---------------------------------------------------------------------------
# P-R2: symlink-escape boundary — a manifest entry pointing to a file that
# resolves outside agents_dir (via symlink) must be rejected with a clear
# diagnostic, not silently followed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_registry_rejects_symlink_escaping_agents_dir(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "phase1").mkdir(parents=True)
    (agents_dir / "index.yaml").write_text(
        "schema_version: 1\nspecialists:\n  - name: trav\n    phase: 1\n    file: phase1/trav.md\n"
    )
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: trav\n---\nbody\n")
    (agents_dir / "phase1" / "trav.md").symlink_to(outside)

    with pytest.raises(SpecialistError, match="escapes agents directory"):
        load_registry(agents_dir)


# ---------------------------------------------------------------------------
# P-R3: duplicate file: paths across distinct manifest entries are rejected
# (Decision-C3 1:1 file-stem ↔ name invariant).
# ---------------------------------------------------------------------------


_DUPLICATE_FILE = _REGISTRY_FIXTURES / "duplicate_file_agents"


@pytest.mark.unit
def test_load_registry_rejects_duplicate_file_path() -> None:
    with pytest.raises(SpecialistError, match="duplicate file path"):
        load_registry(_DUPLICATE_FILE)


# ---------------------------------------------------------------------------
# P-R11: hidden/dotted .md files (e.g. .template.md, editor swap files) are
# explicitly skipped during orphan detection and do NOT trigger
# "orphan specialist" errors.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_registry_skips_dotfile_markdown_in_orphan_check(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "index.yaml").write_text("schema_version: 1\nspecialists: []\n")
    # Drop a dotfile-prefixed markdown into the tree — must NOT trigger orphan.
    (agents_dir / ".template.md").write_text("---\nname: ignored\n---\nbody\n")
    reg = load_registry(agents_dir)
    assert reg.names() == frozenset()


# ---------------------------------------------------------------------------
# P-R14: _VALID_PHASES must derive from the canonical _PHASE_LITERAL in
# _manifest — invariant test pinning that the two locations cannot drift.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_phases_derives_from_manifest_phase_literal() -> None:
    from typing import get_args

    from sdlc.specialists._manifest import _PHASE_LITERAL
    from sdlc.specialists._registry import _VALID_PHASES

    assert frozenset(get_args(_PHASE_LITERAL)) == _VALID_PHASES
    assert frozenset({0, 1, 2, 3}) == _VALID_PHASES


# ---------------------------------------------------------------------------
# P-R9: SpecialistRegistry's MappingProxyType must defensively copy in
# __post_init__ — even if a caller retains a reference to the underlying
# dict and mutates it, the registry's view stays isolated.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_registry_post_init_defensively_copies_specialists() -> None:
    from types import MappingProxyType

    from sdlc.specialists._frontmatter import load_specialist

    md_dir = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "specialists"
        / "registry"
        / "valid_agents"
        / "phase1"
    )
    s = load_specialist(md_dir / "alpha-researcher.md")
    backing = {"alpha-researcher": s}
    reg = SpecialistRegistry(_specialists=MappingProxyType(backing))

    # Mutate the original dict — registry must NOT reflect the mutation.
    backing.clear()
    backing["surprise"] = s
    assert reg.names() == frozenset({"alpha-researcher"})
    assert "surprise" not in reg.names()

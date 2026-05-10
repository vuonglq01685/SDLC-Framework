"""SpecialistRegistry + load_registry (AC3, AC4, Story 2A.2).

SpecialistRegistry is the ONLY public way to enumerate specialists.
Direct calls to load_specialist outside specialists/ and tests are a
code-review-blocking pattern (Architecture §1064).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from sdlc.errors import SpecialistError
from sdlc.specialists._frontmatter import Specialist, load_specialist
from sdlc.specialists._manifest import _parse_manifest

_VALID_PHASES = frozenset({0, 1, 2, 3})
_INDEX_YAML = "index.yaml"


@dataclass(frozen=True)
class SpecialistRegistry:
    """Immutable registry of loaded specialists (manifest-enforced, Decision C3)."""

    _specialists: MappingProxyType[str, Specialist] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def get(self, name: str) -> Specialist:
        """Return the specialist with the given name; raises SpecialistError on miss."""
        try:
            return self._specialists[name]
        except KeyError as exc:
            raise SpecialistError(
                f"unknown specialist {name!r}",
                details={"name": name, "available": sorted(self._specialists)},
            ) from exc

    def list_phase(self, phase: int) -> tuple[Specialist, ...]:
        """Return specialists for a phase sorted by name; raises on invalid phase."""
        if phase not in _VALID_PHASES:
            raise SpecialistError(
                f"invalid phase {phase!r}: must be one of {sorted(_VALID_PHASES)}",
                details={"phase": phase},
            )
        return tuple(
            sorted(
                (s for s in self._specialists.values() if s.phase == phase),
                key=lambda s: s.frontmatter.name,
            )
        )

    def list(self) -> tuple[Specialist, ...]:
        """Return all specialists sorted by name (byte-stable iteration order)."""
        return tuple(sorted(self._specialists.values(), key=lambda s: s.frontmatter.name))

    def names(self) -> frozenset[str]:
        """Return the set of all loaded specialist names."""
        return frozenset(self._specialists)


def load_registry(agents_dir: Path) -> SpecialistRegistry:
    """Build a SpecialistRegistry from agents_dir (Decision C3 manifest-enforced).

    Raises SpecialistError on any failure; never returns a partial registry.
    """
    manifest_path = agents_dir / _INDEX_YAML
    manifest = _parse_manifest(manifest_path)

    # Check for duplicate names in manifest (before any file I/O).
    seen_names: set[str] = set()
    for entry in manifest.specialists:
        if entry.name in seen_names:
            raise SpecialistError(
                f"duplicate specialist name {entry.name!r} in manifest {manifest_path}",
                details={"name": entry.name, "manifest": str(manifest_path)},
            )
        seen_names.add(entry.name)

    # Check for manifest entries pointing to missing files.
    for entry in manifest.specialists:
        file_path = agents_dir / entry.file
        if not file_path.exists():
            raise SpecialistError(
                f"manifest entry refers to missing file: {entry.name} → {entry.file}",
                details={
                    "name": entry.name,
                    "file": str(file_path),
                    "manifest": str(manifest_path),
                },
            )

    # Load all specialists from manifest; attach phase from manifest entry (Decision C3).
    specialists: dict[str, Specialist] = {}
    for entry in manifest.specialists:
        loaded = load_specialist(agents_dir / entry.file)
        # Replace with phase from manifest (frontmatter has no phase field).
        specialists[entry.name] = Specialist(
            frontmatter=loaded.frontmatter,
            body=loaded.body,
            source_path=loaded.source_path,
            phase=entry.phase,
        )

    # Detect orphan markdown files (files under agents_dir not listed in manifest).
    manifest_files = {(agents_dir / e.file).resolve() for e in manifest.specialists}
    for md_path in agents_dir.rglob("*.md"):
        if md_path.resolve() not in manifest_files:
            raise SpecialistError(
                f"orphan specialist: {md_path.relative_to(agents_dir)} not in manifest",
                details={"path": str(md_path), "manifest": str(manifest_path)},
            )

    return SpecialistRegistry(_specialists=MappingProxyType(specialists))

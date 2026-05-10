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
from sdlc.specialists._manifest import _parse_manifest, _SpecialistManifest

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


def _validate_manifest_entries(
    manifest: _SpecialistManifest,
    agents_dir: Path,
    agents_root: Path,
    manifest_path: Path,
) -> set[Path]:
    """Validate manifest entries; return resolved file paths.

    Raises SpecialistError on: duplicate name, path traversal / symlink escape,
    duplicate file: alias, or missing-on-disk file. Used internally by
    load_registry; extracted to keep load_registry under McCabe cap.
    """
    seen_names: set[str] = set()
    seen_files: set[Path] = set()
    for entry in manifest.specialists:
        if entry.name in seen_names:
            raise SpecialistError(
                f"duplicate specialist name {entry.name!r} in manifest {manifest_path}",
                details={"name": entry.name, "manifest": str(manifest_path)},
            )
        seen_names.add(entry.name)

        file_path = (agents_dir / entry.file).resolve()
        # P-R1 + P-R2: enforce path-traversal + symlink-escape boundary.
        try:
            file_path.relative_to(agents_root)
        except ValueError as exc:
            raise SpecialistError(
                f"manifest entry escapes agents directory: {entry.name} → {entry.file}",
                details={
                    "name": entry.name,
                    "file": str(file_path),
                    "agents_dir": str(agents_root),
                    "hint": "manifest 'file' (or its symlink target) must stay under agents/",
                },
            ) from exc
        # P-R3: detect distinct manifest entries aliasing the same file path.
        if file_path in seen_files:
            raise SpecialistError(
                f"duplicate file path in manifest: {entry.file} referenced by multiple entries",
                details={
                    "name": entry.name,
                    "file": str(file_path),
                    "manifest": str(manifest_path),
                },
            )
        seen_files.add(file_path)
        if not file_path.exists():
            raise SpecialistError(
                f"manifest entry refers to missing file: {entry.name} → {entry.file}",
                details={
                    "name": entry.name,
                    "file": str(file_path),
                    "manifest": str(manifest_path),
                },
            )
    return seen_files


def load_registry(agents_dir: Path) -> SpecialistRegistry:
    """Build a SpecialistRegistry from agents_dir (Decision C3 manifest-enforced).

    Raises SpecialistError on any failure; never returns a partial registry.
    """
    agents_root = agents_dir.resolve()
    manifest_path = agents_dir / _INDEX_YAML
    manifest = _parse_manifest(manifest_path)

    seen_files = _validate_manifest_entries(manifest, agents_dir, agents_root, manifest_path)

    # Load all specialists; attach phase from manifest entry (Decision C3).
    specialists: dict[str, Specialist] = {}
    for entry in manifest.specialists:
        loaded = load_specialist(agents_dir / entry.file)
        specialists[entry.name] = Specialist(
            frontmatter=loaded.frontmatter,
            body=loaded.body,
            source_path=loaded.source_path,
            phase=entry.phase,
        )

    # P-R11: skip dotfile markdown during orphan detection (defense-in-depth;
    # pathlib.rglob with "*.md" already excludes leading-dot names by default).
    for md_path in agents_dir.rglob("*.md"):
        if md_path.name.startswith("."):
            continue
        if md_path.resolve() not in seen_files:
            raise SpecialistError(
                f"orphan specialist: {md_path.relative_to(agents_dir)} not in manifest",
                details={"path": str(md_path), "manifest": str(manifest_path)},
            )

    return SpecialistRegistry(_specialists=MappingProxyType(specialists))

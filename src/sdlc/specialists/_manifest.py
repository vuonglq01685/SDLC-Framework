"""Manifest model + parser for agents/index.yaml (AC1, Story 2A.2).

_SpecialistManifest/_ManifestEntry are PRIVATE to specialists/ — NOT wire-format
contracts, NOT snapshotted in tests/contract_snapshots/v1/ (ADR-024 v1 out-of-scope).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import SpecialistError

# Mirror the slug validator from ids/parsers.py — do NOT roll a separate regex.
_KEBAB_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader that fails-loud on duplicate mapping keys.

    Copied verbatim from src/sdlc/runtime/mock.py:68-103 (AC2 mandate).
    Consolidation of this helper is a future debt item.
    """


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None, f"expected a mapping node, but found {node.id}", node.start_mark
        )
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[no-untyped-call]
    return mapping


_NoDuplicateKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


class _ManifestEntry(StrictModel):
    name: str
    phase: Literal[0, 1, 2, 3]
    file: str = Field(min_length=1)

    @field_validator("name", mode="after")
    @classmethod
    def _validate_kebab(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(f"specialist name must be kebab-case, got {v!r}")
        return v


class _SpecialistManifest(StrictModel):
    """Internal manifest schema — private, not snapshotted (ADR-024 v1 out-of-scope)."""

    schema_version: Literal[1] = 1
    specialists: tuple[_ManifestEntry, ...] = Field(default_factory=tuple, strict=False)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_schema_version(cls, v: object) -> object:
        if type(v) is not int:
            raise ValueError(f"schema_version must be a strict int, got {type(v).__name__}")
        return v


def _parse_manifest(path: Path) -> _SpecialistManifest:
    """Load and validate agents/index.yaml; raises SpecialistError on any failure."""
    if not path.exists():
        raise SpecialistError(
            f"manifest not found: {path}",
            details={"path": str(path), "hint": "ensure agents/index.yaml exists"},
        )
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_NoDuplicateKeysLoader)
    except yaml.YAMLError as exc:
        raise SpecialistError(
            f"manifest YAML parse error: {path}", details={"path": str(path)}
        ) from exc
    if not isinstance(data, dict):
        raise SpecialistError(
            f"manifest must be a YAML mapping, got {type(data).__name__}: {path}",
            details={"path": str(path)},
        )
    try:
        return _SpecialistManifest.model_validate(data)
    except Exception as exc:
        raise SpecialistError(
            f"manifest validation error in {path}: {exc}",
            details={"path": str(path), "error": str(exc)},
        ) from exc

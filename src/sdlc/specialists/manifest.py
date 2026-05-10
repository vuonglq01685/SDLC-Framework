"""Manifest model + parser for agents/index.yaml (AC1, Story 2A.2).

_SpecialistManifest/_ManifestEntry are PRIVATE to specialists/ — NOT wire-format
contracts, NOT snapshotted in tests/contract_snapshots/v1/ (ADR-024 v1 out-of-scope).
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias

import yaml
from pydantic import Field, ValidationError, field_validator

from sdlc.contracts._strict_model import StrictModel
from sdlc.errors import SpecialistError

# Mirror the slug validator from ids/parsers.py — do NOT roll a separate regex.
_KEBAB_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# P-R14: canonical phase enumeration. registry._VALID_PHASES derives from this
# via typing.get_args() so the two locations cannot drift.
_PHASE_LITERAL: TypeAlias = Literal[0, 1, 2, 3]


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """Verbatim copy of mock.py:68-103 — fails on duplicate mapping keys (AC2)."""


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
    phase: _PHASE_LITERAL
    file: str = Field(min_length=1)

    @field_validator("name", mode="after")
    @classmethod
    def _validate_kebab(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(f"specialist name must be kebab-case, got {v!r}")
        return v

    @field_validator("file", mode="after")
    @classmethod
    def _validate_relative_path(cls, v: str) -> str:
        # P-R1 + P-R10: defense-in-depth against path traversal, absolute paths,
        # and Windows-style backslashes. The registry re-checks via resolve().
        if "\\" in v:
            raise ValueError(f"manifest 'file' must use forward slashes, got {v!r}")
        pp = PurePosixPath(v)
        if pp.is_absolute():
            raise ValueError(f"manifest 'file' must be a relative path, got {v!r}")
        if ".." in pp.parts:
            raise ValueError(f"manifest 'file' must not contain '..' segments, got {v!r}")
        return v


class _SpecialistManifest(StrictModel):
    """Internal manifest schema — private, not snapshotted (ADR-024 v1 out-of-scope)."""

    schema_version: Literal[1] = 1
    specialists: tuple[_ManifestEntry, ...] = Field(default_factory=tuple, strict=False)


def _parse_manifest(path: Path) -> _SpecialistManifest:
    """Load and validate agents/index.yaml; raises SpecialistError on any failure."""
    if not path.exists():
        raise SpecialistError(
            f"manifest not found: {path}",
            details={"path": str(path), "hint": "ensure agents/index.yaml exists"},
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecialistError(
            f"cannot read manifest {path}: {exc}",
            details={"path": str(path), "hint": "check file permissions"},
        ) from exc
    except UnicodeDecodeError as exc:
        raise SpecialistError(
            f"manifest {path} is not valid UTF-8: {exc}",
            details={"path": str(path), "hint": "save the file as UTF-8 (no BOM)"},
        ) from exc
    try:
        data = yaml.load(raw_text, Loader=_NoDuplicateKeysLoader)
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
    except ValidationError as exc:
        raise SpecialistError(
            f"manifest validation error in {path}: {exc}",
            details={"path": str(path), "error": str(exc)},
        ) from exc

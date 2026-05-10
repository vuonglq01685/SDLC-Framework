"""Specialist frontmatter loader (AC2, Story 2A.2).

Uses _NoDuplicateKeysLoader — copied verbatim from src/sdlc/runtime/mock.py:68-103.
Consolidation of the loader helper is a future debt item (AC2 note).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from sdlc.contracts.specialist_frontmatter import SpecialistFrontmatter
from sdlc.errors import SpecialistError

_DELIM = "---"


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader that fails-loud on duplicate mapping keys (verbatim copy from mock.py)."""


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


@dataclass(frozen=True)
class Specialist:
    """Loaded specialist: frontmatter + body + source path + manifest phase.

    P-R25: `phase` defaults to None (not 0) so a Specialist returned by
    `load_specialist()` directly is distinguishable from a phase-0 specialist
    registered via `load_registry()`. The registry overrides with the manifest
    entry's int phase; standalone callers see None.
    """

    frontmatter: SpecialistFrontmatter
    body: str
    source_path: Path
    phase: int | None = None


def _split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    """Split text into (frontmatter_yaml, body). Raises SpecialistError if no delimiters."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != _DELIM:
        raise SpecialistError(
            f"missing frontmatter delimiters in {path}",
            details={"path": str(path), "hint": "file must start with '---' frontmatter block"},
        )
    try:
        close_idx = next(i for i, ln in enumerate(lines[1:], 1) if ln.rstrip() == _DELIM)
    except StopIteration as exc:
        raise SpecialistError(
            f"unclosed frontmatter block in {path}",
            details={"path": str(path), "hint": "add closing '---' after frontmatter"},
        ) from exc
    fm_yaml = "".join(lines[1:close_idx])
    body = "".join(lines[close_idx + 1 :])
    return fm_yaml, body


def load_specialist(path: Path) -> Specialist:
    """Load and validate a specialist markdown file; raises SpecialistError on any failure."""
    abs_path = path.resolve()
    try:
        text = abs_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecialistError(
            f"cannot read specialist file {path}: {exc}",
            details={"path": str(path), "hint": "check file exists and is readable"},
        ) from exc
    except UnicodeDecodeError as exc:
        # P-R5: UnicodeDecodeError is a ValueError subclass (not OSError) — wrap
        # explicitly so non-UTF-8 / BOM-prefixed files surface a SpecialistError
        # with a clear remediation hint instead of a raw decode error.
        raise SpecialistError(
            f"specialist file {path} is not valid UTF-8: {exc}",
            details={"path": str(path), "hint": "save the file as UTF-8 (no BOM)"},
        ) from exc

    fm_yaml, body = _split_frontmatter(text, path)

    try:
        raw = yaml.load(fm_yaml, Loader=_NoDuplicateKeysLoader)
    except yaml.YAMLError as exc:
        raise SpecialistError(
            f"YAML parse error in frontmatter of {path}: {exc}",
            details={"path": str(path)},
        ) from exc

    try:
        fm = SpecialistFrontmatter.model_validate(raw)
    except ValidationError as exc:
        # P-R12: narrow from `except Exception` so MemoryError / RecursionError /
        # programmer errors inside pydantic surface as themselves rather than as
        # a misleading "frontmatter validation failed" SpecialistError.
        raise SpecialistError(
            f"frontmatter validation failed in {path}: {exc}",
            details={"path": str(path), "error": str(exc)},
        ) from exc

    if fm.name != abs_path.stem:
        raise SpecialistError(
            f"frontmatter name {fm.name!r} does not match file stem {abs_path.stem!r} in {path}",
            details={
                "path": str(path),
                "frontmatter_name": fm.name,
                "stem": abs_path.stem,
                "hint": "rename the file or update the frontmatter name field",
            },
        )

    return Specialist(frontmatter=fm, body=body, source_path=abs_path)

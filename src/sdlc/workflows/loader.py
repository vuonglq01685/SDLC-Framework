"""Workflow YAML loader with schema validation (Story 2A.1, AC1-AC3).

Public API: load_workflow(path) -> WorkflowSpec

Architecture §831-§834: workflows/ is a pure validator/loader; imports only
errors/, contracts/, ids/. Does NOT import engine, dispatcher, runtime, state,
journal, cli, config, concurrency, or specialists.

WorkflowRegistry is the intended consumer of load_workflow for engine code.
Direct calls to load_workflow outside of workflows/ and tests are a
code-review-blocking pattern (Architecture §1063, AC6 note).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.workflows.sec7_heuristics import (
    MAX_FIELD_LEN,
    check_all_instruction_shapes,
    check_instruction_shape_for_field,
)

# Re-export MAX_FIELD_LEN so callers can import it as workflows.loader.MAX_FIELD_LEN
# per spec line 40. Canonical home is sdlc.workflows.sec7_heuristics; the
# circular-import workaround is documented in Debug Log #2.
__all__ = ("MAX_FIELD_LEN", "load_workflow")

# Required string fields that must be non-empty after schema validation.
# Pydantic's frozen contract has no min_length constraint (AC9: WorkflowSpec
# is at schema_version=1 and not amendable in 2A.1), so we enforce it here.
_REQUIRED_NON_EMPTY_STR_FIELDS: tuple[str, ...] = (
    "name",
    "slash_command",
    "primary_agent",
)


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader subclass that raises on duplicate mapping keys.

    Copied verbatim from src/sdlc/runtime/mock.py:68-103 per Story 2A.1 AC1.
    Do NOT extract a shared helper module — future consolidation is a debt item
    if more than two consumers ever exist.
    """


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    # PyYAML wires constructors per node-tag, so under normal control flow this
    # function only sees MappingNode. The assert documents the invariant; if
    # PyYAML's resolver is ever bypassed (e.g. via ``Loader.construct_object``
    # called with a hand-built node), it surfaces a clear AssertionError
    # rather than corrupting the mapping silently.
    assert isinstance(node, yaml.MappingNode), (
        f"_construct_unique_mapping requires a MappingNode, got {type(node).__name__}"
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
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _safe_repr(value: str) -> str:
    """Render a user-controlled string for log/error embedding.

    Escapes control characters and ANSI escape sequences via ``unicode_escape``
    so a malicious YAML key (e.g. ``"\\x1b[2J\\x1b[H"``) cannot corrupt CI log
    rendering.
    """
    return value.encode("unicode_escape").decode("ascii")


def _extract_unknown_key(exc: ValidationError) -> str | None:
    """Extract the first unknown-field key from a pydantic ValidationError."""
    for err in exc.errors():
        if err.get("type") == "extra_forbidden":
            loc = err.get("loc", ())
            if loc:
                return str(loc[-1])
    return None


def _coerce_iterable_to_tuple(data: dict[object, object], key: str) -> None:
    """Pre-coerce list/tuple/set/frozenset values to tuples.

    YAML may produce list (default), tuple (with ``!!python/tuple``), or set
    (with ``!!set``). The pydantic strict validator only accepts tuple for
    ``tuple[str, ...]`` fields, so we normalize here.
    """
    val = data.get(key)
    if isinstance(val, (list, tuple)):
        data[key] = tuple(val)
    elif isinstance(val, (set, frozenset)):
        # Sort for determinism so YAML !!set tags don't surface order-flicker.
        data[key] = tuple(sorted(val, key=str))


def _read_workflow_text(path: Path) -> str:
    """Read a workflow YAML file with differentiated error reporting."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorkflowError(
            f"workflow file does not exist: {path}",
            details={"path": str(path), "errno": "ENOENT"},
        ) from exc
    except IsADirectoryError as exc:
        raise WorkflowError(
            f"workflow path is a directory, not a file: {path}",
            details={"path": str(path), "errno": "EISDIR"},
        ) from exc
    except PermissionError as exc:
        raise WorkflowError(
            f"workflow file is not readable (permission denied): {path}",
            details={"path": str(path), "errno": "EACCES"},
        ) from exc
    except OSError as exc:
        raise WorkflowError(
            f"cannot read workflow file: {path}",
            details={
                "path": str(path),
                "errno": getattr(exc, "errno", None),
                "error_type": type(exc).__name__,
            },
        ) from exc
    except UnicodeDecodeError as exc:
        raise WorkflowError(
            f"workflow file is not valid UTF-8: {path}",
            details={"path": str(path), "error_type": type(exc).__name__},
        ) from exc


def _parse_workflow_yaml(raw: str, path: Path) -> dict[object, object]:
    """Parse YAML text and assert it produced a non-empty mapping."""
    try:
        data = yaml.load(raw, Loader=_NoDuplicateKeysLoader)
    except yaml.YAMLError as exc:
        raise WorkflowError(
            f"YAML parse error in workflow file: {path}",
            details={"path": str(path), "error_type": type(exc).__name__},
        ) from exc

    if data is None:
        raise WorkflowError(
            f"workflow file is empty or contains only comments: {path}",
            details={"path": str(path), "reason": "empty_or_comments_only"},
        )
    if not isinstance(data, dict):
        raise WorkflowError(
            f"workflow file must be a YAML mapping, got {type(data).__name__}: {path}",
            details={"path": str(path), "actual_type": type(data).__name__},
        )
    return data


def _validate_or_wrap(data: dict[object, object], path: Path) -> WorkflowSpec:
    """Run pydantic validation; wrap ``ValidationError`` with sanitized details."""
    try:
        return WorkflowSpec.model_validate(data, strict=True)
    except ValidationError as exc:
        unknown_key = _extract_unknown_key(exc)
        if unknown_key is not None:
            safe_key = _safe_repr(unknown_key)
            raise WorkflowError(
                f"unknown field '{safe_key}' in workflow file: {path} — "
                "regenerate from schema or remove the field",
                details={"path": str(path), "field": safe_key},
            ) from exc
        # Sanitize: do NOT embed str(exc) — pydantic includes the offending
        # input in its error messages, which would re-emit any SEC-7 payload
        # to logs/UIs that the heuristic was meant to keep out.
        raise WorkflowError(
            f"schema validation failed for workflow file: {path}",
            details={
                "path": str(path),
                "error_type": type(exc).__name__,
                "error_count": len(exc.errors()),
                "field_errors": [
                    {"loc": err.get("loc", ()), "type": err.get("type", "")} for err in exc.errors()
                ],
            },
        ) from exc


def load_workflow(path: Path) -> WorkflowSpec:
    """Load and validate a workflow YAML file against the WorkflowSpec contract.

    Args:
        path: Absolute or repo-relative path to a workflow YAML file.

    Returns:
        A frozen WorkflowSpec instance whose fields mirror the YAML.

    Raises:
        WorkflowError: On I/O error, YAML parse error, unknown key, empty file,
            instruction-shape heuristic match (NFR-SEC-7), or empty required
            string field.
    """
    raw = _read_workflow_text(path)
    data = _parse_workflow_yaml(raw, path)
    # Pre-convert YAML list values to tuples for fields whose pre-validator
    # does not run in mode="before"; the strict=True call below re-enables
    # strict coercion for all other fields.
    _coerce_iterable_to_tuple(data, "parallel_agents")
    _coerce_iterable_to_tuple(data, "postconditions")
    spec = _validate_or_wrap(data, path)
    _check_required_non_empty(spec, path)
    _check_string_fields(spec, path)
    return spec


def _check_required_non_empty(spec: WorkflowSpec, path: Path) -> None:
    """Reject empty strings for fields the contract requires to be non-empty."""
    for fname in _REQUIRED_NON_EMPTY_STR_FIELDS:
        value = getattr(spec, fname, "")
        if isinstance(value, str) and not value.strip():
            raise WorkflowError(
                f"required string field {fname!r} is empty in workflow file: {path}",
                details={"path": str(path), "field": fname, "reason": "empty_string"},
            )


def _iter_string_fields(spec: WorkflowSpec) -> Iterable[tuple[str, str]]:
    """Reflectively yield (qualified_name, value) for every string-typed field.

    Drives the SEC-7 walk from ``WorkflowSpec.model_fields`` so that any new
    string field added to the contract is auto-checked. Includes
    ``write_globs`` keys (agent names — a string injection vector previously
    missed by the hand-list) but excludes ``write_globs`` values (glob
    patterns are structural data, not prompt text — see P9).
    """
    for fname in WorkflowSpec.model_fields:
        if fname in {"schema_version", "write_globs"}:
            continue
        yield from _iter_one_field(spec, fname)
    # write_globs keys (agent names) — sorted for byte-stable iteration order.
    for agent in sorted(spec.write_globs.keys()):
        yield (f"write_globs[key:{agent!r}]", agent)


def _iter_one_field(spec: WorkflowSpec, fname: str) -> Iterable[tuple[str, str]]:
    """Yield (qualified_name, value) entries for a single contract field."""
    value: Any = getattr(spec, fname, None)
    if value is None:
        return
    if isinstance(value, str):
        yield (fname, value)
        return
    if isinstance(value, tuple):
        for i, item in enumerate(value):
            if isinstance(item, str):
                yield (f"{fname}[{i}]", item)


def _check_string_fields(spec: WorkflowSpec, path: Path) -> None:
    """Apply NFR-SEC-7 heuristics to all string-typed fields of a WorkflowSpec.

    Iterates fields reflectively (via ``_iter_string_fields``) so new string
    fields added to ``WorkflowSpec`` are auto-checked without loader changes.
    Slash-command allowlist is applied via ``check_instruction_shape_for_field``
    to avoid false-positives on legitimate command names.
    """
    for field_name, value in _iter_string_fields(spec):
        matched = check_instruction_shape_for_field(field_name, value)
        if matched is not None:
            heuristic_name, _ = matched
            all_matched = check_all_instruction_shapes(value)
            raise WorkflowError(
                f"instruction-shaped string rejected in field {field_name!r} "
                f"of workflow file: {path} (heuristic: {heuristic_name})",
                details={
                    "path": str(path),
                    "field": field_name,
                    "heuristic": heuristic_name,
                    "all_matched_heuristics": list(all_matched),
                },
            )

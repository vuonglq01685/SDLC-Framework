"""Pipeline YAML loading helpers — extracted from conftest.py (LOC cap, NFR-MAINT-3).

PR33 / Extension protocol: when adding new step kinds, (a) add to
``_PERMITTED_STEP_KINDS``; (b) add per-kind required-field validation in
``_validate_pipeline_step``; (c) add a runner branch in the pipeline_runner
fixture in conftest.py; (d) update ``tests/e2e/pipeline/README.md``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Schema-version contract (P19) — bumped when pipeline.yaml shape changes.
# ---------------------------------------------------------------------------

_PIPELINE_YAML_SCHEMA_VERSION: int = 1

# Permitted step kinds. Currently only the 2A.0 shim is exercised.
_PERMITTED_STEP_KINDS: frozenset[str] = frozenset({"engine_dispatch_smoke"})


# ---------------------------------------------------------------------------
# _NoDuplicateKeysLoader — copy-paste from src/sdlc/runtime/mock.py per ADR-027.
# Copy-paste is intentional; do NOT extract a shared helper in 2A.0 to avoid
# premature abstraction.
# ---------------------------------------------------------------------------


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader subclass that raises on duplicate mapping keys."""


def _construct_unique_mapping(
    loader: yaml.SafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
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


def _validate_pipeline_step(
    pipeline_yaml_path: Path,
    idx: int,
    step: object,
) -> None:
    """Validate a single pipeline.yaml step entry. Raises AssertionError on shape drift.

    Required keys for every step: ``id`` (PR32), ``kind``.
    Required keys for ``engine_dispatch_smoke`` kind: ``prompt``, ``workflow_step``.
    """
    if not isinstance(step, dict):
        raise AssertionError(
            f"{pipeline_yaml_path}: steps[{idx}] must be a mapping, got {type(step).__name__}"
        )
    # PR32: ``id`` is now required for every step (was previously documented in
    # spec example but unvalidated).
    if "id" not in step:
        raise AssertionError(f"{pipeline_yaml_path}: steps[{idx}] missing required key 'id'")
    kind = step.get("kind")
    if kind not in _PERMITTED_STEP_KINDS:
        raise AssertionError(
            f"{pipeline_yaml_path}: steps[{idx}].kind must be one of "
            f"{sorted(_PERMITTED_STEP_KINDS)}, got {kind!r}"
        )
    if kind == "engine_dispatch_smoke":
        for key in ("prompt", "workflow_step"):
            if key not in step:
                raise AssertionError(
                    f"{pipeline_yaml_path}: steps[{idx}] (kind={kind!r}) "
                    f"missing required key {key!r}"
                )


def _load_pipeline_yaml(pipeline_yaml_path: Path) -> dict[str, object]:
    """Load pipeline.yaml with duplicate-key detection + schema validation (P9, P19).

    Validates the ``mock_responses_dir`` field (PR16) — was previously theatre.
    The field MUST equal ``"./mock_responses"`` (the only sanctioned path in
    2A.0); any other value is rejected with an actionable hint.

    Raises:
      AssertionError on schema-version mismatch, missing top-level keys,
      missing per-step required fields, or unknown step kinds.
    """
    raw = yaml.load(
        pipeline_yaml_path.read_text(encoding="utf-8"),
        Loader=_NoDuplicateKeysLoader,
    )
    if not isinstance(raw, dict):
        raise AssertionError(
            f"{pipeline_yaml_path}: top-level must be a mapping, got {type(raw).__name__}"
        )
    spec: dict[str, object] = raw

    schema_version = spec.get("schema_version")
    if schema_version != _PIPELINE_YAML_SCHEMA_VERSION:
        raise AssertionError(
            f"{pipeline_yaml_path}: schema_version mismatch — "
            f"expected {_PIPELINE_YAML_SCHEMA_VERSION}, got {schema_version!r}"
        )

    # PR16: mock_responses_dir is now enforced — was previously declared but
    # ignored (theatre). The runner hardcodes ``scenario_dir / "mock_responses"``,
    # so the YAML field MUST match that path.
    mock_responses_dir = spec.get("mock_responses_dir")
    if mock_responses_dir != "./mock_responses":
        raise AssertionError(
            f"{pipeline_yaml_path}: mock_responses_dir must be './mock_responses' "
            f"(the only sanctioned path in 2A.0), got {mock_responses_dir!r}. "
            f"action: set mock_responses_dir to './mock_responses' or drop the field."
        )

    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise AssertionError(
            f"{pipeline_yaml_path}: 'steps' must be a non-empty list, "
            f"got {type(steps).__name__ if steps is not None else 'missing'}"
        )
    for idx, step in enumerate(steps):
        _validate_pipeline_step(pipeline_yaml_path, idx, step)

    return spec

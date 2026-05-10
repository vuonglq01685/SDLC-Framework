"""Tier-2 pipeline conftest: MockAIRuntime-driven pipeline replay harness (AC3, AC4).

Defines: pipeline_runner fixture, mock_runtime_factory fixture,
assert_pipeline_goldens helper, PipelineObservation dataclass, and the
dispatch_panel_smoke shim (2A.0 placeholder; Story 2A.3 replaces it wholesale).

Tier-2 runs in-process. Permitted imports: sdlc.runtime, sdlc.errors, sdlc.contracts.
MUST NOT import from sdlc.cli, sdlc.engine, sdlc.dispatcher (not yet stable).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import yaml

from sdlc.errors import MockMissError
from sdlc.runtime.mock import MockAIRuntime

# ---------------------------------------------------------------------------
# Schema-version contract (P19) — bumped when pipeline.yaml shape changes.
# ---------------------------------------------------------------------------

_PIPELINE_YAML_SCHEMA_VERSION: int = 1

# Permitted step kinds. Update when adding new step kinds; tests currently only
# exercise ``engine_dispatch_smoke`` (the 2A.0 shim).
_PERMITTED_STEP_KINDS: frozenset[str] = frozenset({"engine_dispatch_smoke"})


# ---------------------------------------------------------------------------
# _NoDuplicateKeysLoader for pipeline.yaml — copy-paste from mock.py per ADR-027.
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
    """Validate a single pipeline.yaml step entry. Raises AssertionError on shape drift."""
    if not isinstance(step, dict):
        raise AssertionError(
            f"{pipeline_yaml_path}: steps[{idx}] must be a mapping, got {type(step).__name__}"
        )
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

    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise AssertionError(
            f"{pipeline_yaml_path}: 'steps' must be a non-empty list, "
            f"got {type(steps).__name__ if steps is not None else 'missing'}"
        )
    for idx, step in enumerate(steps):
        _validate_pipeline_step(pipeline_yaml_path, idx, step)

    return spec


# ---------------------------------------------------------------------------
# Canonical JSON helper (Architecture §496-§515, Story 1.21 AC1.3)
# ---------------------------------------------------------------------------


def _canon_json(obj: object) -> bytes:
    """Canonicalize to JSON bytes per Architecture §496-§515 rule (Story 1.21 AC1.3).

    Uses indent=2 for PR-diff legibility (ADR-024 §Rationale) + sort_keys for
    byte-stability + compact separators for determinism.
    """
    return (
        json.dumps(
            obj,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


# ---------------------------------------------------------------------------
# PipelineObservation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineObservation:
    """Captures the observable outputs of a Tier-2 pipeline replay run."""

    final_journal_path: Path
    signoff_hashes: tuple[dict[str, object], ...]
    hook_chain: tuple[dict[str, object], ...]
    specialist_invocations: tuple[dict[str, object], ...]


# ---------------------------------------------------------------------------
# 2A.0 shim — dispatch_panel_smoke
#
# Story 2A.3 replaces this shim wholesale with the real dispatcher.
# Its purpose is to prove MockAIRuntime integrates with asyncio.run end-to-end
# before the real dispatcher exists (AC3.2).
# ---------------------------------------------------------------------------


async def _dispatch_panel_smoke(
    mock_runtime: MockAIRuntime,
    prompt: str,
    workflow_step: str,
) -> tuple[dict[str, object] | None, bool]:
    """Placeholder smoke dispatch: awaits MockAIRuntime.dispatch once.

    Returns (invocation_record, mock_miss_raised). The invocation record is
    ``None`` when the dispatch raised ``MockMissError`` (P3: previously the
    record was constructed BEFORE awaiting, which produced a phantom successful-
    invocation entry in goldens even when the mock missed).
    """
    try:
        await mock_runtime.dispatch(prompt=prompt, context={"workflow_step": workflow_step})
    except MockMissError:
        return None, True
    invocation: dict[str, object] = {
        "specialist_id": workflow_step,
        "kind": "primary",
        "write_glob_set": [],
    }
    return invocation, False


# ---------------------------------------------------------------------------
# Async-runner helper (P18): tolerate already-running event loop.
# ---------------------------------------------------------------------------


def _run_coro_blocking(coro: object) -> None:
    """Execute *coro* to completion, tolerating a pre-existing event loop.

    ``asyncio.run`` raises ``RuntimeError`` if a loop is already running (e.g.,
    when ``pytest-asyncio`` is active in another mode). Falls back to spinning
    a fresh loop in that case so Tier-2 tests run regardless of plugin state.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is None:
        asyncio.run(coro)  # type: ignore[arg-type]
        return
    # A loop is already running — use a new loop to drive the coro to completion.
    new_loop = asyncio.new_event_loop()
    try:
        new_loop.run_until_complete(coro)  # type: ignore[arg-type]
    finally:
        new_loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_runtime_factory(
    request: pytest.FixtureRequest,
) -> Callable[[Path], MockAIRuntime]:
    """Return a factory that builds MockAIRuntime from a scenario's ``mock_responses/``.

    Per-test fixture (function scope, P12): previous session-scoped + path-keyed
    cache silently shared a single runtime across tests, masking inter-test
    state leakage and producing tautological "deterministic replay" results.
    Function scope guarantees each test gets a fresh runtime.

    Pre-checks ``mock_responses/`` existence (P21) so a typo or missing scenario
    fails fast with an actionable message instead of a cryptic constructor error.
    """

    def _factory(scenario_dir: Path) -> MockAIRuntime:
        mock_dir = (scenario_dir / "mock_responses").resolve()
        if not mock_dir.is_dir():
            raise FileNotFoundError(
                f"mock_responses/ missing under scenario {scenario_dir}: "
                f"expected {mock_dir} to exist and be a directory. "
                f"action: create the directory and add at least one *.yaml fixture."
            )
        return MockAIRuntime(fixtures_dir=mock_dir)

    return _factory


@pytest.fixture
def pipeline_runner(
    mock_runtime_factory: Callable[[Path], MockAIRuntime],
) -> Callable[[Path, Path], PipelineObservation]:
    """Return a synchronous callable that drives a pipeline scenario and returns observations.

    Tests are plain ``def test_*`` (NOT async); the runner-fixture pattern
    encapsulates async execution internally (AC4 choice: runner-fixture path).

    Path conventions reflect the actual state writer (per the 2026-05-10 P26/D3
    spec amendment): ``<tmp_path>/.claude/state/journal.log``. When 2A.3 lands a
    real journal-writing dispatcher, the same path is observed by both Tier-1
    and Tier-2 — eliminating the latent ``.sdlc`` vs ``.claude`` divergence.
    """

    def _run(scenario_dir: Path, tmp_path: Path) -> PipelineObservation:
        spec = _load_pipeline_yaml(scenario_dir / "pipeline.yaml")
        mock_runtime = mock_runtime_factory(scenario_dir)
        specialist_invocations: list[dict[str, object]] = []
        mock_miss_errors: list[str] = []

        async def _replay() -> None:
            for step in cast(list[dict[str, object]], spec["steps"]):
                kind = step["kind"]
                if kind == "engine_dispatch_smoke":
                    invocation, miss = await _dispatch_panel_smoke(
                        mock_runtime,
                        prompt=str(step["prompt"]),
                        workflow_step=str(step["workflow_step"]),
                    )
                    if miss:
                        mock_miss_errors.append(
                            f"MockMissError for step={step['workflow_step']} "
                            f"prompt={step['prompt']!r}"
                        )
                    elif invocation is not None:
                        specialist_invocations.append(invocation)
                else:
                    raise ValueError(f"Unknown step kind {kind!r} in pipeline.yaml")

        _run_coro_blocking(_replay())

        # Explicit absence check: do NOT rely on "no exception => pass" (AC3.3).
        assert not mock_miss_errors, "MockMissError raised during pipeline replay:\n" + "\n".join(
            mock_miss_errors
        )

        # P26/D3: align with Tier-1's `.claude/state/journal.log`. The smoke shim
        # writes nothing today; the path becomes load-bearing in Story 2A.3.
        journal_path = tmp_path / ".claude" / "state" / "journal.log"
        return PipelineObservation(
            final_journal_path=journal_path,
            signoff_hashes=tuple(),
            hook_chain=tuple(),
            specialist_invocations=tuple(specialist_invocations),
        )

    return _run


# ---------------------------------------------------------------------------
# Central assertion helper
# ---------------------------------------------------------------------------


def assert_pipeline_goldens(
    scenario_dir: Path,
    observed: PipelineObservation,
    update: bool,
) -> None:
    """Assert (or update) the four Tier-2 golden files (AC3.3).

    Golden files under <scenario_dir>/goldens/:
      final_journal_sha256       — raw-bytes sha256 of journal.log or '<no-journal>'
      signoff_hashes.json        — canonical JSON array of phase signoff records
      hook_chain_order.json      — canonical JSON array of hook-fire records
      specialist_invocations.json — canonical JSON array of dispatch records
    """
    goldens_dir = scenario_dir / "goldens"
    goldens_dir.mkdir(parents=True, exist_ok=True)

    journal_hash = (
        hashlib.sha256(observed.final_journal_path.read_bytes()).hexdigest() + "\n"
        if observed.final_journal_path.exists()
        else "<no-journal>\n"
    )

    _action_hint = (
        "action: review the diff. If intentional, regenerate via "
        "'pytest tests/e2e/pipeline/ --update-goldens' and cite the change in the PR Change Log."
    )

    actuals: dict[str, bytes] = {
        "final_journal_sha256": journal_hash.encode("utf-8"),
        "signoff_hashes.json": _canon_json(list(observed.signoff_hashes)),
        "hook_chain_order.json": _canon_json(list(observed.hook_chain)),
        "specialist_invocations.json": _canon_json(list(observed.specialist_invocations)),
    }

    if update:
        for filename, content in actuals.items():
            (goldens_dir / filename).write_bytes(content)
        return

    errors: list[str] = []
    for filename, actual in actuals.items():
        golden_path = goldens_dir / filename
        if not golden_path.exists():
            errors.append(f"Golden file missing: {golden_path}\n{_action_hint}")
            continue
        expected = golden_path.read_bytes()
        if actual != expected:
            errors.append(
                f"GOLDEN MISMATCH: {golden_path}\n"
                f"  expected: {expected!r}\n"
                f"  actual:   {actual!r}\n"
                f"{_action_hint}"
            )

    if errors:
        raise AssertionError("\n\n".join(errors))

"""Tier-2 pipeline conftest: MockAIRuntime-driven pipeline replay harness (AC3, AC4).

Defines: pipeline_runner fixture, mock_runtime_factory fixture,
PipelineObservation dataclass, and the dispatch_panel_smoke shim (2A.0
placeholder; Story 2A.3 replaces it wholesale).

Tier-2 runs in-process. Permitted imports: sdlc.runtime, sdlc.errors, sdlc.contracts.
MUST NOT import from sdlc.cli, sdlc.engine, sdlc.dispatcher (not yet stable).

PR-DR3 sanctioned signature: ``pipeline_runner`` is a synchronous callable
``(scenario_dir: Path, tmp_path: Path) -> PipelineObservation`` — the spec's
prior coroutine-yielding wording is amended to allow the sync wrapper because
``_run_coro_blocking`` encapsulates the asyncio entry. PR-DR6 sanctioned: the
``_canon_json`` indent=2 deviation is sanctioned for human-reviewable goldens.

LOC note: YAML-loading helpers live in ``_yaml_loader.py``; golden-assertion
helpers live in ``_golden_assert.py`` (NFR-MAINT-3 LOC cap compliance).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from e2e.pipeline._golden_assert import _canon_json, assert_pipeline_goldens
from e2e.pipeline._yaml_loader import _load_pipeline_yaml
from sdlc.errors import MockMissError
from sdlc.runtime.mock import MockAIRuntime

# Explicit re-exports so mypy --strict treats these as part of this module's API.
__all__ = ["_canon_json", "_load_pipeline_yaml", "assert_pipeline_goldens"]

# ---------------------------------------------------------------------------
# PipelineObservation
# ---------------------------------------------------------------------------


def _freeze_records(
    records: list[dict[str, object]] | tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], ...]:
    """Wrap each dict in ``MappingProxyType`` so callers can't mutate goldens (PR22).

    ``@dataclass(frozen=True)`` only freezes attribute binding, not contents.
    Wrapping individual records makes ``obs.signoff_hashes[0]["phase"] = …``
    raise ``TypeError`` instead of silently mutating replay state.
    """
    return tuple(
        record if isinstance(record, MappingProxyType) else MappingProxyType(dict(record))
        for record in records
    )


@dataclass(frozen=True)
class PipelineObservation:
    """Captures the observable outputs of a Tier-2 pipeline replay run.

    Items in tuples are wrapped via :class:`MappingProxyType` (PR22) so callers
    can't mutate them post-construction. Construct via the
    :func:`PipelineObservation.create` classmethod to ensure freezing.
    """

    final_journal_path: Path
    signoff_hashes: tuple[Mapping[str, object], ...]
    hook_chain: tuple[Mapping[str, object], ...]
    specialist_invocations: tuple[Mapping[str, object], ...]

    @classmethod
    def create(
        cls,
        *,
        final_journal_path: Path,
        signoff_hashes: list[dict[str, object]] | tuple[Mapping[str, object], ...] = (),
        hook_chain: list[dict[str, object]] | tuple[Mapping[str, object], ...] = (),
        specialist_invocations: list[dict[str, object]] | tuple[Mapping[str, object], ...] = (),
    ) -> PipelineObservation:
        """Build an observation with all record collections frozen (PR22)."""
        return cls(
            final_journal_path=final_journal_path,
            signoff_hashes=_freeze_records(signoff_hashes),
            hook_chain=_freeze_records(hook_chain),
            specialist_invocations=_freeze_records(specialist_invocations),
        )


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
# Async-runner helper (PR4): tolerate already-running event loop.
# ---------------------------------------------------------------------------


def _run_coro_blocking(coro: object) -> None:
    """Execute *coro* to completion, with explicit handling for running-loop case.

    ``asyncio.run`` raises ``RuntimeError`` if a loop is already running (e.g.,
    when ``pytest-asyncio`` is active in another mode). PR4: previously this
    fell back to ``new_event_loop().run_until_complete()`` which Python forbids
    in the same thread → guaranteed ``RuntimeError`` exactly in the case the
    fallback claimed to handle. Now raises a clear, actionable error so callers
    fix the test invocation context (e.g., remove pytest-asyncio mode=auto)
    instead of trapping into an unreachable code path.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is None:
        asyncio.run(coro)  # type: ignore[arg-type]
        return
    raise RuntimeError(
        "_run_coro_blocking called while another event loop is running. "
        "Tier-2 tests must run as plain `def test_*`, not `async def`. "
        "Check pytest-asyncio configuration (mode=auto enables async fixtures) "
        "and ensure the test does not run inside an async context."
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_runtime_factory() -> Callable[[Path], MockAIRuntime]:
    """Return a factory that builds MockAIRuntime from a scenario's ``mock_responses/``.

    Per-test fixture (function scope, P12): previous session-scoped + path-keyed
    cache silently shared a single runtime across tests, masking inter-test
    state leakage and producing tautological "deterministic replay" results.
    Function scope guarantees each test gets a fresh runtime.

    Pre-checks ``mock_responses/`` existence (P21) so a typo or missing scenario
    fails fast with an actionable message instead of a cryptic constructor error.

    PR7: previous fixture accepted an unused ``request: pytest.FixtureRequest``
    parameter that hinted at a finalizer that was never registered. The
    parameter is removed; cleanup is implicit via per-test scope (each test gets
    a fresh ``MockAIRuntime`` whose ``_load_fixtures`` is read-only).
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
        return PipelineObservation.create(
            final_journal_path=journal_path,
            specialist_invocations=specialist_invocations,
        )

    return _run

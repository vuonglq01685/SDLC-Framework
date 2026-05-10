"""Tier-2 pipeline tests — happy_path_smoke scenario (MockAIRuntime dispatch).

Proves MockAIRuntime integrates with asyncio.run end-to-end before the real
dispatcher lands in Story 2A.3 (AC3.2). Tests are plain def (NOT async);
asyncio is encapsulated by pipeline_runner (AC4 runner-fixture pattern).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from e2e.pipeline.conftest import (
    PipelineObservation,
    _canon_json,
    assert_pipeline_goldens,
)

pytestmark = pytest.mark.e2e

_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "happy_path_smoke"

# Type alias for the pipeline_runner fixture's return type.
_PipelineRunner = Callable[[Path, Path], PipelineObservation]


def test_happy_path_smoke_goldens(
    tmp_path: Path,
    pipeline_runner: _PipelineRunner,
    update_goldens: bool,
) -> None:
    """Smoke scenario: single MockAIRuntime dispatch with four byte-stable goldens."""
    observation = pipeline_runner(_SCENARIO_DIR, tmp_path)
    assert_pipeline_goldens(_SCENARIO_DIR, observation, update_goldens)


def test_happy_path_smoke_deterministic_replay(
    tmp_path: Path,
    pipeline_runner: _PipelineRunner,
) -> None:
    """Replay-determinism invariant: same scenario run twice produces byte-identical
    observations.

    P2 — Two distinct runtimes (function-scoped ``mock_runtime_factory``) drive
    two distinct ``tmp_path`` subtrees. The test byte-compares the canonical
    serializations of every observable artifact between runs, not just dataclass
    equality, so silent non-determinism in the canonicalizer or MockAIRuntime
    cannot slip past as a tautology (AC5).
    """
    tmp_path1 = tmp_path / "run1"
    tmp_path1.mkdir()
    tmp_path2 = tmp_path / "run2"
    tmp_path2.mkdir()

    obs_run1 = pipeline_runner(_SCENARIO_DIR, tmp_path1)
    obs_run2 = pipeline_runner(_SCENARIO_DIR, tmp_path2)

    # In-memory observation equality (cheap pre-check).
    assert obs_run1.specialist_invocations == obs_run2.specialist_invocations, (
        "specialist_invocations differed between run 1 and run 2"
    )
    assert obs_run1.signoff_hashes == obs_run2.signoff_hashes, (
        "signoff_hashes differed between runs"
    )
    assert obs_run1.hook_chain == obs_run2.hook_chain, "hook_chain differed between runs"

    # Byte-level determinism: canonical JSON serialization must be identical
    # across runs for every observation field. (Catches non-determinism that
    # ``==`` would miss, e.g., dict iteration order leaking into JSON.)
    for field_name in ("specialist_invocations", "signoff_hashes", "hook_chain"):
        bytes1 = _canon_json([dict(r) for r in getattr(obs_run1, field_name)])
        bytes2 = _canon_json([dict(r) for r in getattr(obs_run2, field_name)])
        assert bytes1 == bytes2, (
            f"{field_name} canonical JSON differed between runs:\n"
            f"  run1: {bytes1!r}\n"
            f"  run2: {bytes2!r}"
        )

    # Journal hash determinism: both runs must produce the same hash sentinel
    # (or content hash if a future shim writes one).
    def _journal_hash(observation: PipelineObservation) -> str:
        if observation.final_journal_path.exists():
            return hashlib.sha256(observation.final_journal_path.read_bytes()).hexdigest()
        return "<no-journal>"

    hash1 = _journal_hash(obs_run1)
    hash2 = _journal_hash(obs_run2)
    assert hash1 == hash2, (
        f"final_journal hash differed between runs: run1={hash1!r} run2={hash2!r}"
    )

    # Distinct paths confirm we drove two independent runtimes (not a tautology).
    assert obs_run1.final_journal_path != obs_run2.final_journal_path, (
        "Both runs reported the same journal path — runs were not isolated"
    )

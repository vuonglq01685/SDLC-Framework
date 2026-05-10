"""Anti-tautology tests — Tier-2 pipeline harness + mock-miss (AC6).

These are THE MOST IMPORTANT tests in Story 2A.0. Split from
``test_harness_anti_tautology.py`` to stay under the 400-line LOC cap
(Architecture §765 + NFR-MAINT-3). PR8: spec File List + AC6 wording amended
to acknowledge the split.

Invariant classes tested here:
  1. Mutation receipt — harness fails when a pipeline golden is corrupted (AC6.1 Tier-2).
  2. Mock-miss surfaces clearly — MockMissError names step and prompt_hash (AC6.2).

Tier-1 CLI + CI anti-leakage + ``_safe_corrupt`` sanity tests live in
``test_harness_anti_tautology.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from e2e._anti_tautology_helpers import (
    _bootstrap_pipeline_scenario,
    _safe_corrupt,
)
from e2e.pipeline.conftest import assert_pipeline_goldens
from sdlc.errors import MockMissError
from sdlc.runtime.mock import MockAIRuntime

pytestmark = pytest.mark.e2e

_PIPELINE_SMOKE_SCENARIO = Path(__file__).parent / "pipeline" / "fixtures" / "happy_path_smoke"


# ===========================================================================
# AC6.1 — Mutation receipt: Tier-2 pipeline harness fails on corrupted goldens
# ===========================================================================


def test_mutation_pipeline_specialist_invocations_corruption_detected(
    tmp_path: Path,
) -> None:
    """P13 — Tier-2 harness fails when specialist_invocations.json golden is corrupted."""
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    golden = scenario_dir / "goldens" / "specialist_invocations.json"
    golden.write_bytes(
        b'[{"specialist_id":"<<CORRUPTED>>","kind":"primary","write_glob_set":[]}]\n'
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    assert "specialist_invocations.json" in str(exc_info.value), (
        f"Expected 'specialist_invocations.json' in error; got:\n{exc_info.value}"
    )


def test_mutation_pipeline_signoff_hashes_corruption_detected(
    tmp_path: Path,
) -> None:
    """P13 — Tier-2 harness fails when signoff_hashes.json golden is corrupted."""
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    golden = scenario_dir / "goldens" / "signoff_hashes.json"
    golden.write_bytes(b'[{"phase":"<<CORRUPTED>>"}]\n')

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    assert "signoff_hashes.json" in str(exc_info.value), (
        f"Expected 'signoff_hashes.json' in error; got:\n{exc_info.value}"
    )


def test_mutation_pipeline_hook_chain_corruption_detected(
    tmp_path: Path,
) -> None:
    """P13 — Tier-2 harness fails when hook_chain_order.json golden is corrupted."""
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    golden = scenario_dir / "goldens" / "hook_chain_order.json"
    golden.write_bytes(b'[{"hook_name":"<<CORRUPTED>>"}]\n')

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    assert "hook_chain_order.json" in str(exc_info.value), (
        f"Expected 'hook_chain_order.json' in error; got:\n{exc_info.value}"
    )


def test_mutation_pipeline_final_journal_corruption_detected(
    tmp_path: Path,
) -> None:
    """P13 — Tier-2 harness fails when final_journal_sha256 golden is corrupted."""
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    golden = scenario_dir / "goldens" / "final_journal_sha256"
    golden.write_text("deadbeef" * 8 + "\n", encoding="utf-8")

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    assert "final_journal_sha256" in str(exc_info.value), (
        f"Expected 'final_journal_sha256' in error; got:\n{exc_info.value}"
    )


def test_mutation_pipeline_golden_deletion_detected(
    tmp_path: Path,
) -> None:
    """P13 — Tier-2 harness fails with 'Golden file missing' when a pipeline golden is deleted."""
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    (scenario_dir / "goldens" / "specialist_invocations.json").unlink()

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    msg = str(exc_info.value)
    assert "Golden file missing" in msg, f"Expected 'Golden file missing' in error; got:\n{msg}"
    assert "specialist_invocations.json" in msg, (
        f"Expected 'specialist_invocations.json' in error; got:\n{msg}"
    )


# ===========================================================================
# AC6.2 — Mock-miss surfaces clearly
# ===========================================================================


def test_mock_miss_raises_with_step_and_hash(tmp_path: Path) -> None:
    """MockMissError is raised with (step, prompt_hash) when fixture key is absent.

    PR31: prompt hash is now computed via ``hashlib.sha256`` instead of
    hardcoded — if ``_hash_prompt`` ever changes encoding, the test self-detects.
    """
    mock_dir = tmp_path / "mock_responses"
    mock_dir.mkdir()
    wrong_hash = "sha256:" + "0" * 64
    (mock_dir / "_smoke.yaml").write_text(
        f'"{wrong_hash}":\n'
        "  output_text: wrong\n"
        "  tool_calls: []\n"
        "  tokens_in: 1\n"
        "  tokens_out: 1\n",
        encoding="utf-8",
    )

    mock_runtime = MockAIRuntime(fixtures_dir=mock_dir)

    prompt = "smoke test prompt"
    with pytest.raises(MockMissError) as exc_info:
        asyncio.run(
            mock_runtime.dispatch(
                prompt=prompt,
                context={"workflow_step": "_smoke"},
            )
        )

    error_msg = str(exc_info.value)
    assert "_smoke" in error_msg, f"Expected '_smoke' in MockMissError; got:\n{error_msg}"
    # PR31: compute the expected hash so the assertion self-validates against
    # any future change to MockAIRuntime's prompt-hash encoding.
    expected_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert expected_hash in error_msg, (
        f"Expected prompt hash {expected_hash!r} in MockMissError; got:\n{error_msg}"
    )


# ===========================================================================
# AC6.3 — --update-goldens cannot mask a pipeline regression
# ===========================================================================


def test_update_goldens_pipeline_cannot_mask_regression(
    tmp_path: Path,
) -> None:
    """AC6.3 — Tier-2 harness catches corruption applied after --update-goldens.

    Bootstraps goldens with update=True, then corrupts a golden, then asserts
    update=False fails — proving pipeline goldens cannot be laundered by a
    subsequent manual edit.
    """
    scenario_dir, obs = _bootstrap_pipeline_scenario(tmp_path, _PIPELINE_SMOKE_SCENARIO)

    golden = scenario_dir / "goldens" / "specialist_invocations.json"
    original = golden.read_bytes()
    golden.write_bytes(_safe_corrupt(original))

    with pytest.raises(AssertionError) as exc_info:
        assert_pipeline_goldens(scenario_dir, obs, update=False)

    assert "specialist_invocations.json" in str(exc_info.value), (
        f"Expected 'specialist_invocations.json' in error; got:\n{exc_info.value}"
    )

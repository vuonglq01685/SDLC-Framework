"""Anti-tautology tests — Tier-1 CLI harness (AC6).

These are THE MOST IMPORTANT tests in Story 2A.0.  Without them the harness is
just another way to ship Pattern 1 (tautological/placebo) defects from the
Epic 1 retro (§3).  Each test deliberately breaks an invariant and asserts the
harness FAILS with a clear, actionable error message.

Invariant classes tested here:
  1. Mutation receipt — harness fails when a CLI golden is corrupted (Tier-1).
  2. --update-goldens cannot mask a real bug (AC6.3).
  3. CI-anti-leakage — ``--update-goldens`` MUST NOT appear in CI (AC2.5).
  4. Sanity asserts for _safe_corrupt itself.

Tier-2 pipeline + mock-miss tests live in
``test_harness_anti_tautology_pipeline.py``.

Import resolution note (P15):
  ``from e2e.cli.conftest import ...`` resolves because pytest's
  ``--import-mode=prepend`` (configured in pyproject.toml) prepends ``tests/``
  to sys.path.  Do NOT add ``tests/__init__.py`` — it breaks rootdir detection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e._anti_tautology_helpers import (
    _bootstrap_cli_scenario,
    _safe_corrupt,
)
from e2e.cli.conftest import (
    _SKIP_NO_UV,
    _SKIP_WIN32,
    assert_goldens,
)
from e2e.pipeline.conftest import _canon_json

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WALKING_SKELETON_SCENARIO = Path(__file__).parent / "cli" / "fixtures" / "walking_skeleton"


# ===========================================================================
# AC6.1 — Mutation receipt: Tier-1 CLI harness fails on corrupted goldens
# ===========================================================================


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_stdout_byte_flip_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """Harness fails when 01_init.stdout golden has a single byte flipped."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    stdout_golden = scenario_dir / "goldens" / "01_init.stdout"
    original = stdout_golden.read_bytes()
    stdout_golden.write_bytes(_safe_corrupt(original))

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.stdout" in str(exc_info.value), (
        f"Expected '01_init.stdout' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_exit_code_bump_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """Harness fails when 01_init.exit golden is bumped from 0 to 1."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    exit_golden = scenario_dir / "goldens" / "01_init.exit"
    exit_golden.write_text("1\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.exit" in str(exc_info.value), (
        f"Expected '01_init.exit' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_journal_hash_corruption_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """Harness fails when 02_scan.journal_sha256 golden contains a wrong hex."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    journal_hash_golden = scenario_dir / "goldens" / "02_scan.journal_sha256"
    journal_hash_golden.write_text("deadbeef" * 8 + "\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"

    result_init = cli_runner(["init"], project_dir2)  # type: ignore[operator]
    assert_goldens(scenario_dir, "01_init", result_init, sdlc_dir2, project_dir2, update=True)

    result_scan = cli_runner(["scan"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "02_scan", result_scan, sdlc_dir2, project_dir2, update=False)

    assert "02_scan.journal_sha256" in str(exc_info.value), (
        f"Expected '02_scan.journal_sha256' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_state_hash_corruption_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """P13 — Harness fails when 01_init.state_sha256 golden contains a wrong hex."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    state_hash_golden = scenario_dir / "goldens" / "01_init.state_sha256"
    state_hash_golden.write_text("cafebabe" * 8 + "\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.state_sha256" in str(exc_info.value), (
        f"Expected '01_init.state_sha256' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_stderr_corruption_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """P13 — Harness fails when 01_init.stderr golden has unexpected content injected.

    The walking_skeleton scenario produces empty stderr; injecting a sentinel
    byte sequence proves the empty-stderr lane is not a free pass.
    """
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    stderr_golden = scenario_dir / "goldens" / "01_init.stderr"
    stderr_golden.write_bytes(b"<<UNEXPECTED-STDERR>>\n")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.stderr" in str(exc_info.value), (
        f"Expected '01_init.stderr' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_golden_deletion_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """P13 — Harness fails with 'Golden file missing' when a golden is deleted."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    deleted_golden = scenario_dir / "goldens" / "01_init.stdout"
    deleted_golden.unlink()

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    msg = str(exc_info.value)
    assert "Golden file missing" in msg, f"Expected 'Golden file missing' in error; got:\n{msg}"
    assert "01_init.stdout" in msg, f"Expected '01_init.stdout' in error; got:\n{msg}"


# ===========================================================================
# AC6.3 — --update-goldens cannot mask a real bug
# ===========================================================================


@_SKIP_NO_UV
def test_update_goldens_cannot_mask_semantic_regression(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """--update-goldens regenerates goldens but cannot hide manual post-update corruption.

    Simulates a developer captures output via --update-goldens, then someone
    edits the golden after the fact; a subsequent non-update run correctly fails.
    The deterministic-replay variant lives in
    ``test_update_goldens_replay_disagreement_detected`` (P25).
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sdlc_dir = project_dir / ".claude"
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "goldens").mkdir()

    result = cli_runner(["init"], project_dir)  # type: ignore[operator]
    assert_goldens(scenario_dir, "01_init", result, sdlc_dir, project_dir, update=True)

    stdout_golden = scenario_dir / "goldens" / "01_init.stdout"
    assert stdout_golden.exists(), "Golden should have been written by --update-goldens"
    captured_stdout = stdout_golden.read_text(encoding="utf-8")
    assert captured_stdout != "", "Captured golden should be non-empty"

    stdout_golden.write_text("STALE_OUTPUT_FROM_BROKEN_BUILD\n", encoding="utf-8")

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir, project_dir, update=False)

    error_msg = str(exc_info.value)
    assert "01_init.stdout" in error_msg, (
        f"Expected '01_init.stdout' in AssertionError; got:\n{error_msg}"
    )
    assert "action: review the diff" in error_msg, (
        f"Expected action hint in AssertionError; got:\n{error_msg}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_update_goldens_replay_disagreement_detected(
    tmp_path: Path,
    cli_runner: object,
) -> None:
    """P25 / AC6.3 — harness catches production code that disagrees with itself.

    Spec scenario: developer runs ``--update-goldens`` once (captures output A),
    then production-code non-determinism causes the next run to produce output B
    (different from A).  The harness MUST detect the disagreement on the next
    non-update run.

    Simulation: drive ``--update-goldens`` against a fresh project_dir, capture
    the golden bytes, then mutate them to simulate a SECOND ``--update-goldens``
    run that produced DIFFERENT bytes.  A final non-update run against the
    mutated golden MUST fail and name the offending artifact.
    """
    project_dir1 = tmp_path / "project1"
    project_dir1.mkdir()
    sdlc_dir1 = project_dir1 / ".claude"
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "goldens").mkdir()

    # Run #1 with --update-goldens — captures golden A.
    result1 = cli_runner(["init"], project_dir1)  # type: ignore[operator]
    assert_goldens(scenario_dir, "01_init", result1, sdlc_dir1, project_dir1, update=True)
    golden_a_bytes = (scenario_dir / "goldens" / "01_init.stdout").read_bytes()
    assert golden_a_bytes, "Run #1 should have captured non-empty golden"

    # Simulate run #2 producing DIFFERENT bytes (non-determinism failure mode).
    golden_b_bytes = _safe_corrupt(golden_a_bytes)
    (scenario_dir / "goldens" / "01_init.stdout").write_bytes(golden_b_bytes)

    # Run #3 (no --update-goldens) re-executes the SAME command.  Production
    # output matches golden A but on-disk golden is B — harness MUST fail.
    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result2 = cli_runner(["init"], project_dir2)  # type: ignore[operator]

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result2, sdlc_dir2, project_dir2, update=False)

    error_msg = str(exc_info.value)
    assert "01_init.stdout" in error_msg, (
        f"Expected '01_init.stdout' in disagreement-detection error; got:\n{error_msg}"
    )
    assert "action: review the diff" in error_msg, (
        f"Expected action hint in disagreement-detection error; got:\n{error_msg}"
    )


# ===========================================================================
# AC2.5 — CI never passes --update-goldens (P1)
# ===========================================================================


def test_ci_workflow_does_not_pass_update_goldens() -> None:
    """P1 / AC2.5 — ``--update-goldens`` MUST NOT appear in ``.github/workflows/ci.yml``.

    The flag is a developer regeneration tool only; CI must NEVER run with it,
    or every regression would self-heal silently.
    """
    ci_yml = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_yml.is_file(), f"CI workflow not found at {ci_yml}"
    contents = ci_yml.read_text(encoding="utf-8")
    assert "--update-goldens" not in contents, (
        f"CI MUST NOT pass --update-goldens (found in {ci_yml}). "
        f"Regenerating goldens in CI would silently launder real regressions."
    )


# ===========================================================================
# Sanity asserts for the safe-corruption helper itself (defense in depth).
# ===========================================================================


def test_safe_corrupt_rejects_empty() -> None:
    """P4 — _safe_corrupt MUST reject empty input rather than write a sentinel."""
    with pytest.raises(AssertionError):
        _safe_corrupt(b"")


def test_safe_corrupt_changes_input() -> None:
    """P4 — _safe_corrupt always returns a different byte sequence (UTF-8 valid)."""
    for sample in (b"hello", b"a", b"x\n", b"012345", b'{"k":"v"}'):
        corrupted = _safe_corrupt(sample)
        assert corrupted != sample, f"Failed to corrupt {sample!r}"
        corrupted.decode("utf-8")


def test_safe_corrupt_handles_non_ascii() -> None:
    """P4 — _safe_corrupt falls back to suffix append when no printable-ASCII byte exists."""
    sample = bytes([0xFF, 0xFE, 0xFD])
    corrupted = _safe_corrupt(sample)
    assert corrupted != sample
    assert corrupted.endswith(b"<<CORRUPTED>>")


def test_canon_json_is_deterministic_across_calls() -> None:
    """Sanity — _canon_json must produce identical bytes for identical inputs."""
    sample = [{"b": 2, "a": 1}, {"y": "z", "x": "w"}]
    runs = [_canon_json(sample) for _ in range(5)]
    assert all(r == runs[0] for r in runs), f"Canonicalization not deterministic: {runs!r}"
    parsed = json.loads(runs[0])
    assert list(parsed[0].keys()) == ["a", "b"], "sort_keys did not reorder map keys"

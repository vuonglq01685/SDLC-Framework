"""Anti-tautology tests — Tier-1 CLI harness (AC6).

These are THE MOST IMPORTANT tests in Story 2A.0. Without them the harness is
just another way to ship Pattern 1 (tautological/placebo) defects from the
Epic 1 retro (§3). Each test deliberately breaks an invariant and asserts the
harness FAILS with a clear, actionable error message.

Invariant classes tested here:
  1. Mutation receipt — harness fails when a CLI golden is corrupted (Tier-1).
  2. ``--update-goldens`` cannot mask a real bug (AC6.3).
  3. Runtime divergence — harness fails when subprocess output changes vs.
     captured golden, proving production-code regressions are caught (PR-DR5).
  4. CI-anti-leakage — ``--update-goldens`` MUST NOT appear in any CI workflow
     (AC2.5, PR17 — scans all ``.github/workflows/*.yml``).

Schema-version drift + ``_safe_corrupt`` sanity tests live in
``test_harness_anti_tautology_schema.py`` (LOC-cap split, NFR-MAINT-3).
Tier-2 pipeline + mock-miss tests live in
``test_harness_anti_tautology_pipeline.py``.

Import resolution note (P15 / PR2):
  ``from e2e.cli.conftest import ...`` resolves because pytest's
  ``--import-mode=prepend`` (configured in pyproject.toml) prepends ``tests/``
  to sys.path. Do NOT add ``tests/__init__.py`` — it breaks rootdir detection.
  PR2: the prior P15 description ("add tests/__init__.py") is misleading; the
  real fix relies on rootdir conftest path resolution as documented above.
"""

from __future__ import annotations

import subprocess
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
from e2e.conftest import CliRunner

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
    cli_runner: CliRunner,
) -> None:
    """Harness fails when 01_init.stdout golden has a single byte flipped."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    stdout_golden = scenario_dir / "goldens" / "01_init.stdout"
    original = stdout_golden.read_bytes()
    stdout_golden.write_bytes(_safe_corrupt(original))

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.stdout" in str(exc_info.value), (
        f"Expected '01_init.stdout' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_exit_code_bump_detected(
    tmp_path: Path,
    cli_runner: CliRunner,
) -> None:
    """Harness fails when 01_init.exit golden is bumped from 0 to 1."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    exit_golden = scenario_dir / "goldens" / "01_init.exit"
    exit_golden.write_text("1\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.exit" in str(exc_info.value), (
        f"Expected '01_init.exit' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_journal_hash_corruption_detected(
    tmp_path: Path,
    cli_runner: CliRunner,
) -> None:
    """Harness fails when 02_scan.journal_sha256 golden contains a wrong hex."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    journal_hash_golden = scenario_dir / "goldens" / "02_scan.journal_sha256"
    journal_hash_golden.write_text("deadbeef" * 8 + "\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"

    result_init = cli_runner(["init"], project_dir2)
    assert_goldens(scenario_dir, "01_init", result_init, sdlc_dir2, project_dir2, update=True)

    result_scan = cli_runner(["scan"], project_dir2)

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "02_scan", result_scan, sdlc_dir2, project_dir2, update=False)

    assert "02_scan.journal_sha256" in str(exc_info.value), (
        f"Expected '02_scan.journal_sha256' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_state_hash_corruption_detected(
    tmp_path: Path,
    cli_runner: CliRunner,
) -> None:
    """P13 — Harness fails when 01_init.state_sha256 golden contains a wrong hex."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    state_hash_golden = scenario_dir / "goldens" / "01_init.state_sha256"
    state_hash_golden.write_text("cafebabe" * 8 + "\n", encoding="utf-8")

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.state_sha256" in str(exc_info.value), (
        f"Expected '01_init.state_sha256' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_stderr_corruption_detected(
    tmp_path: Path,
    cli_runner: CliRunner,
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
    result = cli_runner(["init"], project_dir2)

    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "01_init", result, sdlc_dir2, project_dir2, update=False)

    assert "01_init.stderr" in str(exc_info.value), (
        f"Expected '01_init.stderr' in error; got:\n{exc_info.value}"
    )


@_SKIP_NO_UV
@_SKIP_WIN32
def test_mutation_golden_deletion_detected(
    tmp_path: Path,
    cli_runner: CliRunner,
) -> None:
    """P13 — Harness fails with 'Golden file missing' when a golden is deleted."""
    scenario_dir, _ = _bootstrap_cli_scenario(tmp_path, cli_runner, _WALKING_SKELETON_SCENARIO)

    deleted_golden = scenario_dir / "goldens" / "01_init.stdout"
    deleted_golden.unlink()

    project_dir2 = tmp_path / "project2"
    project_dir2.mkdir()
    sdlc_dir2 = project_dir2 / ".claude"
    result = cli_runner(["init"], project_dir2)

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
    cli_runner: CliRunner,
) -> None:
    """--update-goldens regenerates goldens but cannot hide manual post-update corruption.

    Simulates a developer captures output via --update-goldens, then someone
    edits the golden after the fact; a subsequent non-update run correctly fails.
    The runtime-divergence variant lives in
    ``test_assert_goldens_catches_runtime_divergence`` (PR-DR5).
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sdlc_dir = project_dir / ".claude"
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "goldens").mkdir()

    result = cli_runner(["init"], project_dir)
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


def test_assert_goldens_catches_runtime_divergence(tmp_path: Path) -> None:
    """PR-DR5 / AC6.3 — harness fires when SUBPROCESS OUTPUT changes vs captured golden.

    Distinct from ``test_update_goldens_cannot_mask_semantic_regression`` (which
    edits the on-disk golden): this test holds the golden constant and synthesizes
    two ``CompletedProcess`` objects with different stdout, proving the harness
    compares **runtime-fresh subprocess output** to the captured golden — i.e.,
    that a production-code regression that emits divergent output is caught.

    Pattern-1 closure: previous ``test_update_goldens_replay_disagreement_detected``
    was a tautological clone (corrupt-then-rerun pattern, identical to the
    semantic-regression test). This test substitutes a synthesized result so the
    "runtime output" lane is exercised independently of subprocess + filesystem.
    """
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "goldens").mkdir()
    sdlc_dir = tmp_path / ".claude"

    # Synthesize two CompletedProcess objects representing two runs of the same
    # command, where production code regressed between runs to emit different
    # stdout.
    fake_args: list[str] = ["uv", "run", "sdlc", "--no-color", "init"]
    result_a: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        fake_args,
        returncode=0,
        stdout="Initialized SDLC framework in <TMP>\n",
        stderr="",
    )
    result_b: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
        fake_args,
        returncode=0,
        stdout="REGRESSED_PRODUCTION_OUTPUT — DIFFERENT FROM RUN A\n",
        stderr="",
    )

    # Capture golden from result_a via update=True.
    assert_goldens(scenario_dir, "fake_cmd", result_a, sdlc_dir, tmp_path, update=True)
    captured = (scenario_dir / "goldens" / "fake_cmd.stdout").read_text(encoding="utf-8")
    assert "Initialized" in captured, (
        f"--update-goldens should have captured result_a.stdout; got: {captured!r}"
    )

    # Now run with result_b (DIFFERENT stdout) and update=False.
    # The harness MUST detect that runtime output diverges from on-disk golden.
    with pytest.raises(AssertionError) as exc_info:
        assert_goldens(scenario_dir, "fake_cmd", result_b, sdlc_dir, tmp_path, update=False)

    error = str(exc_info.value)
    assert "fake_cmd.stdout" in error, (
        f"Expected runtime-divergence error to name 'fake_cmd.stdout'; got:\n{error}"
    )
    assert "REGRESSED" in error or "GOLDEN MISMATCH" in error, (
        f"Expected divergence detail in error; got:\n{error}"
    )


# ===========================================================================
# AC2.5 — CI never passes --update-goldens (P1, PR17 — all workflow files)
# ===========================================================================


def test_ci_workflows_do_not_pass_update_goldens() -> None:
    """P1 / AC2.5 / PR17 — ``--update-goldens`` MUST NOT appear in any CI workflow.

    Scans ALL ``.github/workflows/*.{yml,yaml}`` files (was previously only
    ``ci.yml``). A contributor adding the flag to ``e2e.yml`` or any other
    workflow would otherwise launder real regressions silently.

    The flag is a developer regeneration tool only; CI must NEVER run with it.
    """
    workflows_dir = _REPO_ROOT / ".github" / "workflows"
    assert workflows_dir.is_dir(), f"CI workflows dir not found at {workflows_dir}"
    workflow_files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    assert workflow_files, f"No CI workflow files found under {workflows_dir}"

    offenders: list[str] = []
    for wf in workflow_files:
        if "--update-goldens" in wf.read_text(encoding="utf-8"):
            offenders.append(str(wf.relative_to(_REPO_ROOT)))

    assert not offenders, (
        "--update-goldens MUST NOT appear in CI workflows. Found in:\n"
        + "\n".join(f"  - {f}" for f in offenders)
        + "\nRegenerating goldens in CI would silently launder real regressions."
    )

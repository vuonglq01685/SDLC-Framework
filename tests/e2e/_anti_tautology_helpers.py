"""Shared bootstrap helpers for anti-tautology test modules.

Extracted from test_harness_anti_tautology.py to stay under the 400-line LOC
cap (Architecture §765 + NFR-MAINT-3). Contains:
  - _safe_corrupt     — UTF-8-safe byte-level corruption helper (P4)
  - _fresh_scenario_dir  — isolated scenario copy with goldens wiped (P17)
  - _bootstrap_cli_scenario   — Tier-1 CLI golden bootstrap shim
  - _bootstrap_pipeline_scenario — Tier-2 pipeline bootstrap shim

Do NOT add test functions here; this file is a helper module, not a test
collection.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import cast

from e2e.cli.conftest import assert_goldens, load_commands_yaml
from e2e.conftest import CliRunner
from e2e.pipeline.conftest import (
    PipelineObservation,
    _dispatch_panel_smoke,
    _load_pipeline_yaml,
    assert_pipeline_goldens,
)
from sdlc.runtime.mock import MockAIRuntime


def _safe_corrupt(original: bytes) -> bytes:
    """Return a byte-different version of *original* that remains UTF-8 decodable.

    Targets the first printable-ASCII byte (32 ≤ b ≤ 126) and toggles its low
    bit (XOR 0x01), which always yields another printable ASCII byte.

    Asserts ``original`` is non-empty AND UTF-8 decodable (PR6: previously the
    fallback for non-printable inputs returned ``original + b"<<CORRUPTED>>"``
    which silently produced invalid UTF-8 when ``original`` itself was not
    UTF-8 decodable). Callers must pre-flight non-printable / non-UTF-8 inputs.

    The original P4 sentinel-suffix fallback is kept ONLY for inputs that decode
    cleanly but happen to contain no printable-ASCII bytes (rare; e.g. all-newline
    files). In that case the suffix is ``"<<CORRUPTED>>"`` — pure ASCII, so
    decoding remains valid.
    """
    assert original, (
        "Cannot corrupt an empty/missing source — anti-tautology precondition violated. "
        "Investigate why the source file is empty."
    )
    # PR6: enforce the UTF-8-decodable precondition explicitly. The function
    # contract promises decodable output; the only way to honor that is to
    # demand decodable input.
    try:
        original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"_safe_corrupt input is not UTF-8 decodable ({exc}). "
            f"action: ensure the file under test contains valid UTF-8 before corruption."
        ) from exc

    for idx, byte in enumerate(original):
        if 32 <= byte <= 126:
            mutated = byte ^ 0x01
            corrupted = original[:idx] + bytes([mutated]) + original[idx + 1 :]
            assert corrupted != original
            return corrupted
    # All bytes outside printable-ASCII (e.g. all-newline file). Suffix sentinel
    # is pure ASCII, so the result remains UTF-8 decodable.
    corrupted = original + b"<<CORRUPTED>>"
    assert corrupted != original
    return corrupted


def _fresh_scenario_dir(tmp_path: Path, scenario_src: Path, name: str = "scenario") -> Path:
    """Copy *scenario_src* into *tmp_path/name* with goldens dir wiped.

    Always rmtree's the destination first (P17) so reruns and ordering changes
    can't leak stale goldens from a prior partial run.

    PR11: asserts that the destination is under ``tmp_path`` so accidental
    write-back into the source-tree scenario fixtures is impossible. This is
    defense-in-depth; ``tmp_path`` is pytest-managed so the assertion always
    holds, but a future refactor that passes a non-tmp path to ``name`` would
    fail loudly.
    """
    scenario_dir = tmp_path / name
    # PR11 guard: scenario_dir MUST resolve under tmp_path.
    try:
        scenario_dir.resolve().relative_to(tmp_path.resolve())
    except ValueError as exc:
        raise AssertionError(
            f"_fresh_scenario_dir refuses to write outside tmp_path. "
            f"tmp_path={tmp_path}, scenario_dir={scenario_dir}. "
            f"action: ensure the bootstrap helpers are called with pytest's tmp_path."
        ) from exc

    if scenario_dir.exists():
        shutil.rmtree(scenario_dir)
    shutil.copytree(scenario_src, scenario_dir)
    goldens_dir = scenario_dir / "goldens"
    if goldens_dir.exists():
        shutil.rmtree(goldens_dir)
    goldens_dir.mkdir()
    return scenario_dir


def _bootstrap_cli_scenario(
    tmp_path: Path,
    cli_runner: CliRunner,
    scenario_src: Path,
) -> tuple[Path, Path]:
    """Copy scenario, run all commands, and bootstrap goldens.

    Returns (scenario_dir, project_dir). On Windows, 02_scan is skipped so
    the test's own platform-skip stays in sync with the harness platform-skip.

    PR9: ``cli_runner`` is now typed as ``CliRunner`` Protocol (not ``object``).
    """
    scenario_dir = _fresh_scenario_dir(tmp_path, scenario_src)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sdlc_dir = project_dir / ".claude"

    spec = load_commands_yaml(scenario_dir / "commands.yaml")
    for cmd in cast(list[dict[str, object]], spec["commands"]):
        if cmd["id"] == "02_scan" and sys.platform == "win32":
            continue
        result = cli_runner(cast(list[str], cmd["args"]), project_dir)
        assert_goldens(scenario_dir, str(cmd["id"]), result, sdlc_dir, project_dir, update=True)

    return scenario_dir, project_dir


def _bootstrap_pipeline_scenario(
    tmp_path: Path,
    scenario_src: Path,
) -> tuple[Path, PipelineObservation]:
    """Copy pipeline scenario into tmp_path, drive it once with update=True, return obs.

    The anti-tautology tests live one directory above ``tests/e2e/pipeline/``,
    so the ``pipeline_runner`` fixture is not auto-loaded. This helper
    instantiates the runtime + dispatch shim directly via the imported helpers,
    mirroring ``pipeline_runner``'s behaviour without fixture indirection.

    PR20: replicates the ``mock_responses/`` pre-check from
    ``mock_runtime_factory`` so a typo or missing scenario fails fast with the
    same actionable hint instead of bypassing the safety net.
    """
    scenario_dir = _fresh_scenario_dir(tmp_path, scenario_src, name="pipeline_scenario")
    run_tmp = tmp_path / "pipeline_run"
    run_tmp.mkdir()

    spec = _load_pipeline_yaml(scenario_dir / "pipeline.yaml")
    mock_dir = (scenario_dir / "mock_responses").resolve()
    # PR20: same pre-check as mock_runtime_factory (P21 mirror).
    if not mock_dir.is_dir():
        raise FileNotFoundError(
            f"mock_responses/ missing under scenario {scenario_dir}: "
            f"expected {mock_dir} to exist and be a directory. "
            f"action: create the directory and add at least one *.yaml fixture."
        )
    mock_runtime = MockAIRuntime(fixtures_dir=mock_dir)

    invocations: list[dict[str, object]] = []
    miss_errors: list[str] = []

    async def _replay() -> None:
        for step in cast(list[dict[str, object]], spec["steps"]):
            invocation, miss = await _dispatch_panel_smoke(
                mock_runtime,
                prompt=str(step["prompt"]),
                workflow_step=str(step["workflow_step"]),
            )
            if miss:
                miss_errors.append(str(step["workflow_step"]))
            elif invocation is not None:
                invocations.append(invocation)

    asyncio.run(_replay())
    assert not miss_errors, f"Unexpected MockMissError(s) during bootstrap: {miss_errors}"

    obs = PipelineObservation.create(
        final_journal_path=run_tmp / ".claude" / "state" / "journal.log",
        specialist_invocations=invocations,
    )
    assert_pipeline_goldens(scenario_dir, obs, update=True)
    return scenario_dir, obs

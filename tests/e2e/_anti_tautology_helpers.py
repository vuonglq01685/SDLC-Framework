"""Shared bootstrap helpers for anti-tautology test modules.

Extracted from test_harness_anti_tautology.py to stay under the 400-line LOC
cap (Architecture §765 + NFR-MAINT-3).  Contains:
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
    bit (XOR 0x01), which always yields another printable ASCII byte.  Falls
    back to appending a sentinel suffix if no printable-ASCII byte exists.

    Asserts ``original`` is non-empty and the result differs (P4: prevents the
    self-defeating tautology where corrupting an empty file silently writes a
    sentinel and the test "passes" without exercising the invariant).
    """
    assert original, (
        "Cannot corrupt an empty/missing source — anti-tautology precondition violated. "
        "Investigate why the source file is empty."
    )
    for idx, byte in enumerate(original):
        if 32 <= byte <= 126:
            mutated = byte ^ 0x01
            corrupted = original[:idx] + bytes([mutated]) + original[idx + 1 :]
            assert corrupted != original
            return corrupted
    # No printable-ASCII byte — append a sentinel.
    corrupted = original + b"<<CORRUPTED>>"
    assert corrupted != original
    return corrupted


def _fresh_scenario_dir(tmp_path: Path, scenario_src: Path, name: str = "scenario") -> Path:
    """Copy *scenario_src* into *tmp_path/name* with goldens dir wiped.

    Always rmtree's the destination first (P17) so reruns and ordering changes
    can't leak stale goldens from a prior partial run.
    """
    scenario_dir = tmp_path / name
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
    cli_runner: object,
    scenario_src: Path,
) -> tuple[Path, Path]:
    """Copy scenario, run all commands, and bootstrap goldens.

    Returns (scenario_dir, project_dir).  On Windows, 02_scan is skipped so
    the test's own platform-skip stays in sync with the harness platform-skip.
    """
    scenario_dir = _fresh_scenario_dir(tmp_path, scenario_src)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sdlc_dir = project_dir / ".claude"

    spec = load_commands_yaml(scenario_dir / "commands.yaml")
    for cmd in cast(list[dict[str, object]], spec["commands"]):
        if cmd["id"] == "02_scan" and sys.platform == "win32":
            continue
        result = cli_runner(cmd["args"], project_dir)  # type: ignore[operator]
        assert_goldens(scenario_dir, str(cmd["id"]), result, sdlc_dir, project_dir, update=True)

    return scenario_dir, project_dir


def _bootstrap_pipeline_scenario(
    tmp_path: Path,
    scenario_src: Path,
) -> tuple[Path, PipelineObservation]:
    """Copy pipeline scenario into tmp_path, drive it once with update=True, return obs.

    The anti-tautology tests live one directory above ``tests/e2e/pipeline/``,
    so the ``pipeline_runner`` fixture is not auto-loaded.  This helper
    instantiates the runtime + dispatch shim directly via the imported helpers,
    mirroring ``pipeline_runner``'s behaviour without fixture indirection.
    """
    scenario_dir = _fresh_scenario_dir(tmp_path, scenario_src, name="pipeline_scenario")
    run_tmp = tmp_path / "pipeline_run"
    run_tmp.mkdir()

    spec = _load_pipeline_yaml(scenario_dir / "pipeline.yaml")
    mock_dir = (scenario_dir / "mock_responses").resolve()
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

    obs = PipelineObservation(
        final_journal_path=run_tmp / ".claude" / "state" / "journal.log",
        signoff_hashes=tuple(),
        hook_chain=tuple(),
        specialist_invocations=tuple(invocations),
    )
    assert_pipeline_goldens(scenario_dir, obs, update=True)
    return scenario_dir, obs

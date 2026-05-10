"""Tier-1 CLI golden tests — walking skeleton scenario (init → scan → status).

Exercises the seed scenario against the shipped CLI surface (Stories 1.16/1.17).
Proves the Tier-1 harness works end-to-end before Epic 2A code exists (AC2).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from e2e.cli.conftest import (
    _SKIP_NO_UV,
    _SKIP_WIN32,
    assert_goldens,
    load_commands_yaml,
)
from e2e.conftest import CliRunner

pytestmark = pytest.mark.e2e

_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "walking_skeleton"

# 02_scan uses journal.append_sync (POSIX-only flock). The full three-command
# sequence is skipped on Windows; init-only coverage is provided here by
# test_walking_skeleton_init_only_no_win32_skip (AC5.4).
#
# P22 NOTE — 03_status is not separately Windows-runnable in 2A.0:
# `sdlc status` output depends on whether `sdlc scan` ran, so a Windows-runnable
# status test requires a *separate* goldens set captured from the init→status
# (no-scan) flow under e.g. `fixtures/walking_skeleton_no_scan/`. Deferred to a
# future story per AC5.4 partial coverage. The init+status-on-Windows path is
# currently exercised end-to-end by `tests/integration/test_walking_skeleton_e2e.py`
# (Story 1.16/1.17), which provides defense-in-depth for that subset.


@_SKIP_NO_UV
@_SKIP_WIN32
def test_walking_skeleton_goldens(
    tmp_path: Path,
    cli_runner: CliRunner,
    update_goldens: bool,
) -> None:
    """Full walking skeleton: init → scan → status with byte-stable golden verification.

    The command sequence shares a single project root (tmp_path) — NOT per-command —
    mirroring the real CLI lifecycle (AC2.1).
    """
    sdlc_dir = tmp_path / ".claude"
    spec = load_commands_yaml(_SCENARIO_DIR / "commands.yaml")

    for cmd in cast(list[dict[str, object]], spec["commands"]):
        result = cli_runner(cast(list[str], cmd["args"]), tmp_path)
        assert_goldens(
            _SCENARIO_DIR,
            str(cmd["id"]),
            result,
            sdlc_dir,
            tmp_path,
            update_goldens,
        )


@_SKIP_NO_UV
def test_walking_skeleton_init_only_no_win32_skip(
    tmp_path: Path,
    cli_runner: CliRunner,
    update_goldens: bool,
) -> None:
    """Verify the harness correctly asserts the 01_init golden on all platforms.

    Runs only init (POSIX-independent) to prove Windows-compatible subset coverage.
    The golden for 01_init is shared with test_walking_skeleton_goldens so both
    tests must agree on the expected output.
    """
    sdlc_dir = tmp_path / ".claude"
    result = cli_runner(["init"], tmp_path)
    assert_goldens(_SCENARIO_DIR, "01_init", result, sdlc_dir, tmp_path, update_goldens)

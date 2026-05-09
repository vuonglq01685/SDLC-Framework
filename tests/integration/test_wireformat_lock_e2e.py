"""End-to-end smoke tests for the wire-format lock ceremony (Story 1.21, AC7.4).

Runs the full pipeline via subprocess to verify the freeze script and immutability
pytest gate both exit 0 on a clean repo with committed snapshots.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only invariants in repo state"),
]

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def test_freeze_script_exits_0_on_clean_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/freeze_wireformat_snapshots.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"freeze_wireformat_snapshots.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "5 contracts match snapshots" in result.stdout


def test_immutability_pytest_gate_exits_0() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contracts/test_wireformat_immutability.py",
            "-v",
            "--no-cov",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"pytest tests/contracts/test_wireformat_immutability.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

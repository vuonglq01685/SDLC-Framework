"""AC2 Tier-1 (Story 3.7, spec line 44): source-tree-write mutation classes MUST be killed.

The aggregate >=95% kill gate (``scripts/run_adopt_mutation.py``) can be satisfied while a single
catastrophic mutant survives. These tests pin the *most dangerous* mutation classes directly, so
any mutation that lets adopt write to — or escape — the source tree flips a test to RED (a recorded
kill) independent of the aggregate:

  * the ``.claude/`` write-confinement guard (``assert_path_under_claude``) — the barrier that keeps
    every adopt write inside the sandbox;
  * the sandbox-integrity seam (``assert_source_untouched``);
  * (POSIX) the symlink-create path never copies or rewrites a source file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sdlc.adopt.invariant import assert_path_under_claude, assert_source_untouched
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "outside_target",
    ["src/main.py", "pom.xml", "README.md", "lib/util.py", "../escape.txt"],
)
def test_write_target_outside_claude_is_rejected(tmp_path: Path, outside_target: str) -> None:
    """A weakened .claude/ containment guard would let adopt write into source — this kills it."""
    (tmp_path / ".claude").mkdir()
    with pytest.raises(AdoptError):
        assert_path_under_claude(tmp_path, tmp_path / outside_target)


def test_write_target_inside_claude_is_allowed(tmp_path: Path) -> None:
    """Companion positive case so an always-raise mutant of the guard is also killed."""
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    assert_path_under_claude(tmp_path, tmp_path / ".claude" / "state" / "adopt-report.json")


def test_source_untouched_rejects_missing_sandbox(tmp_path: Path) -> None:
    """A mutant that no-ops the sandbox-integrity seam is killed (missing .claude/ must raise)."""
    with pytest.raises(AdoptError):
        assert_source_untouched(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="adopt is POSIX-only (ADR-034)")
def test_adopt_never_rewrites_or_copies_a_source_file(tmp_path: Path) -> None:
    """A mutant redirecting a symlink-create into a copy-into-source mutates source bytes — killed.

    Runs a real non-interactive adopt over a brownfield fixture and asserts every pre-existing
    source file is byte-identical and was not replaced by a symlink/copy.
    """
    # POSIX-only helper (imports the driver); lazy-imported under the win32 skip (ADR-034).
    from adopt._source_untouched_helpers import (
        AdoptInvocationMode,
        copy_fixture,
        init_git_repo,
        run_adopt_for_mode,
        snapshot_source_bytes,
    )

    root = copy_fixture("java-maven-service", tmp_path)
    init_git_repo(root)
    before = snapshot_source_bytes(root)
    assert before, "fixture must contain at least one source file to be a meaningful guard"
    run_adopt_for_mode(root, AdoptInvocationMode.NON_INTERACTIVE_AUTO)
    for rel, original in before.items():
        path = root / rel
        assert path.read_bytes() == original, f"adopt rewrote source file {rel}"
        assert not path.is_symlink(), f"adopt replaced source file {rel} with a symlink"

"""Unit tests for the adopt source-untouched guard (Story 3.1, AC7).

3.1 scope: the orchestrator writes ONLY under `.claude/`. Every write target is
pre-guarded by `assert_path_under_claude`, which raises `AdoptError` (ERR_ADOPT,
exit 2) on any path outside `root/.claude/`. The exhaustive porcelain + tree-hash
property + mutation gate is Story 3.7 — `assert_source_untouched` is the typed seam
3.7 will harden.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sdlc.adopt.invariant import assert_path_under_claude, assert_source_untouched
from sdlc.errors import AdoptError

pytestmark = pytest.mark.unit


def test_path_inside_claude_is_allowed(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    target = tmp_path / ".claude" / "state" / "adopt-report.json"
    # does not raise
    assert_path_under_claude(tmp_path, target)


def test_path_outside_claude_raises_adopt_error(tmp_path: Path) -> None:
    target = tmp_path / "src" / "main.py"
    with pytest.raises(AdoptError) as exc_info:
        assert_path_under_claude(tmp_path, target)
    assert exc_info.value.code == "ERR_ADOPT"


def test_path_traversal_out_of_claude_raises(tmp_path: Path) -> None:
    """A `.claude/../src` path that escapes the sandbox via traversal is rejected."""
    target = tmp_path / ".claude" / ".." / "src" / "evil.py"
    with pytest.raises(AdoptError):
        assert_path_under_claude(tmp_path, target)


def test_claude_dir_itself_is_allowed(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    assert_path_under_claude(tmp_path, tmp_path / ".claude")


def test_assert_source_untouched_requires_claude_dir(tmp_path: Path) -> None:
    """The public seam (architecture.md:1069) validates the .claude sandbox (Story 3.7)."""
    (tmp_path / ".claude").mkdir()
    assert_source_untouched(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="symlink sandbox tests are POSIX-focused")
def test_symlinked_claude_dir_raises(tmp_path: Path) -> None:
    """CR3.1-W2: a symlinked .claude/ must not pass the sandbox guard."""
    real = tmp_path / "real-claude"
    real.mkdir()
    (tmp_path / ".claude").symlink_to(real)
    with pytest.raises(AdoptError):
        assert_path_under_claude(tmp_path, real / "state" / "x.json")


@pytest.mark.skipif(sys.platform == "win32", reason="symlink sandbox tests are POSIX-focused")
def test_claude_resolving_outside_root_raises(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".claude").symlink_to(outside)
    with pytest.raises(AdoptError):
        assert_source_untouched(tmp_path)


def test_missing_claude_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(AdoptError):
        assert_source_untouched(tmp_path)


# --- Story 3.7 AC2: pin the exact message + details of every write-guard rejection so that
# mutations to the error contract (not just the raise/no-raise decision) are killed. ---


def test_write_outside_claude_message_and_details(tmp_path: Path) -> None:
    """The confinement guard's message + details are part of the contract (AC2 Tier-1)."""
    target = tmp_path / "src" / "main.py"
    with pytest.raises(AdoptError) as exc_info:
        assert_path_under_claude(tmp_path, target)
    exc = exc_info.value
    assert exc.code == "ERR_ADOPT"
    assert exc.message == "adopt refuses to write outside .claude/ (source tree is read-only)"
    assert exc.details == {
        "path": str(target),
        "claude_root": str(tmp_path.resolve() / ".claude"),
    }


def test_claude_is_a_regular_file_message_and_details(tmp_path: Path) -> None:
    """`.claude` as a file (not a dir) → typed rejection with exact message + details."""
    (tmp_path / ".claude").write_text("not a directory", encoding="utf-8")
    with pytest.raises(AdoptError) as exc_info:
        assert_source_untouched(tmp_path)
    exc = exc_info.value
    assert exc.code == "ERR_ADOPT"
    assert exc.message == "adopt requires .claude/ to be a directory under the repository root"
    assert exc.details == {"path": str(tmp_path / ".claude")}


@pytest.mark.skipif(sys.platform == "win32", reason="symlink sandbox tests are POSIX-focused")
def test_symlinked_claude_message_and_details(tmp_path: Path) -> None:
    """A symlinked `.claude/` is rejected with the exact symlink message + details (CR3.1-W2)."""
    real = tmp_path / "real-claude"
    real.mkdir()
    (tmp_path / ".claude").symlink_to(real)
    with pytest.raises(AdoptError) as exc_info:
        assert_source_untouched(tmp_path)
    exc = exc_info.value
    assert exc.code == "ERR_ADOPT"
    assert exc.message == "adopt refuses a symlinked .claude/ sandbox"
    assert exc.details == {"path": str(tmp_path / ".claude")}

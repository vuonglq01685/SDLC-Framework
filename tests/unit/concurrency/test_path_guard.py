"""Unit tests for sdlc.concurrency.path_guard.assert_repo_contained (ADR-037 / CR4.12-W1).

RED-first per CONTRIBUTING §2. The guard rejects repo-escaping paths, `..` traversal,
and symlink components (ancestor OR leaf), returning the safe absolute path for a
contained target. Symlink cases are POSIX-only here (symlink creation needs privilege
on Windows) but run on the CI POSIX legs; the escape/traversal/accept cases run on all
hosts, so the core logic is measured locally even on Windows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sdlc.concurrency.path_guard import assert_contained, assert_repo_contained
from sdlc.errors import SecurityError

pytestmark = pytest.mark.unit

_NEEDS_SYMLINK = pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation needs privilege on Windows; exercised on the CI POSIX legs",
)


class TestContainedPathsAccepted:
    def test_relative_path_returns_absolute_under_root(self, tmp_path: Path) -> None:
        target = tmp_path / ".claude" / "state" / "clar" / "open_clarification.md"
        target.parent.mkdir(parents=True)
        result = assert_repo_contained(Path(".claude/state/clar/open_clarification.md"), tmp_path)
        assert result == target.resolve()
        assert result.is_absolute()

    def test_absolute_path_under_root_accepted(self, tmp_path: Path) -> None:
        target = tmp_path / ".claude" / "x.md"
        target.parent.mkdir(parents=True)
        assert assert_repo_contained(target, tmp_path) == target.resolve()

    def test_nonexistent_write_target_accepted(self, tmp_path: Path) -> None:
        # A write target (resolution.md) need not exist yet — the guard must still pass it.
        target = tmp_path / ".claude" / "state" / "resolution.md"
        target.parent.mkdir(parents=True)
        assert assert_repo_contained(target, tmp_path) == target.resolve()


class TestEscapesRejected:
    def test_absolute_path_outside_root_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.md"  # sibling of the repo root
        with pytest.raises(SecurityError):
            assert_repo_contained(outside, tmp_path)

    def test_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(SecurityError):
            assert_repo_contained(Path("../../etc/passwd"), tmp_path)

    @_NEEDS_SYMLINK
    def test_symlinked_ancestor_dir_rejected(self, tmp_path: Path) -> None:
        outside_dir = tmp_path.parent / "outside_dir"
        outside_dir.mkdir()
        (tmp_path / "link").symlink_to(outside_dir, target_is_directory=True)
        with pytest.raises(SecurityError):
            assert_repo_contained(Path("link/x.md"), tmp_path)

    @_NEEDS_SYMLINK
    def test_symlinked_leaf_rejected(self, tmp_path: Path) -> None:
        outside_file = tmp_path.parent / "outside.md"
        outside_file.write_text("x", encoding="utf-8")
        (tmp_path / "link.md").symlink_to(outside_file)
        with pytest.raises(SecurityError):
            assert_repo_contained(Path("link.md"), tmp_path)


class TestErrorShape:
    def test_raises_security_error_with_code(self, tmp_path: Path) -> None:
        with pytest.raises(SecurityError) as exc:
            assert_repo_contained(Path("../escape.md"), tmp_path)
        assert exc.value.code == "ERR_SECURITY"


class TestAssertContainedStaticRoot:
    def test_path_under_static_root_accepted(self, tmp_path: Path) -> None:
        static_root = tmp_path / "static"
        static_root.mkdir()
        asset = static_root / "app.js"
        asset.write_text("x", encoding="utf-8")
        assert assert_contained(asset, static_root) == asset.resolve()

    def test_path_outside_static_root_rejected(self, tmp_path: Path) -> None:
        static_root = tmp_path / "static"
        static_root.mkdir()
        outside = tmp_path / "cli.py"
        outside.write_text("x", encoding="utf-8")
        with pytest.raises(SecurityError):
            assert_contained(outside, static_root)

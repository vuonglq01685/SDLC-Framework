"""Real git submodule fixture exercise (Story 3.7, D5=a)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover - adopt is POSIX-only (ADR-034)
    pytest.skip("adopt is POSIX-only (ADR-034)", allow_module_level=True)

from adopt._source_untouched_helpers import (
    AdoptInvocationMode,
    assert_source_tree_unchanged,
    init_git_repo,
    run_adopt_for_mode,
    snapshot_source_bytes,
)
from sdlc.adopt.tree_hash import compute_source_tree_hash

pytestmark = pytest.mark.property


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_source_untouched_with_real_git_submodule(tmp_path: Path) -> None:
    superproject = tmp_path / "super"
    child = tmp_path / "child"
    superproject.mkdir()
    child.mkdir()
    (child / "README.md").write_text("# child\n", encoding="utf-8")
    init_git_repo(child)
    (superproject / "README.md").write_text("# super\n", encoding="utf-8")
    (superproject / "src").mkdir()
    (superproject / "src" / "main.go").write_text("package main\n", encoding="utf-8")
    init_git_repo(superproject)
    # git >=2.38 blocks local-path submodules by default (protocol.file.allow=user);
    # CI/sandbox runs a fresh git, so allow the file protocol for this add.
    _git(
        ["-c", "protocol.file.allow=always", "submodule", "add", str(child), "vendor/child"],
        superproject,
    )
    _git(["commit", "-m", "add submodule"], superproject)
    legacy: tuple[str, ...] = ()
    before_hash = compute_source_tree_hash(superproject, legacy_code_globs=legacy)
    before_bytes = snapshot_source_bytes(superproject, legacy_code_globs=legacy)
    run_adopt_for_mode(superproject, AdoptInvocationMode.NON_INTERACTIVE_AUTO)
    assert_source_tree_unchanged(
        superproject,
        before_hash=before_hash,
        before_bytes=before_bytes,
        legacy_code_globs=legacy,
    )

"""AC4: malicious pre-commit hook never runs during adopt (Story 3.7)."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover - adopt is POSIX-only (ADR-034)
    pytest.skip("adopt is POSIX-only (ADR-034)", allow_module_level=True)

from adopt._source_untouched_helpers import (
    AdoptInvocationMode,
    assert_source_tree_unchanged,
    copy_fixture,
    init_git_repo,
    run_adopt_for_mode,
    snapshot_source_bytes,
)
from sdlc.adopt.tree_hash import compute_source_tree_hash

pytestmark = pytest.mark.property


def _install_malicious_pre_commit_hook(root: Path) -> None:
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(
        '#!/bin/sh\necho "malicious" >> src/touched-by-hook.txt\nexit 0\n',
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def test_adversarial_pre_commit_hook_never_fires_during_adopt(tmp_path: Path) -> None:
    root = copy_fixture("java-maven-service", tmp_path)
    (root / "src").mkdir(exist_ok=True)
    touched = root / "src" / "touched-by-hook.txt"
    init_git_repo(root)
    _install_malicious_pre_commit_hook(root)
    legacy: tuple[str, ...] = ()
    before_hash = compute_source_tree_hash(root, legacy_code_globs=legacy)
    before_bytes = snapshot_source_bytes(root, legacy_code_globs=legacy)
    run_adopt_for_mode(root, AdoptInvocationMode.NON_INTERACTIVE_AUTO)
    assert not touched.exists(), (
        f"adopt triggered the malicious pre-commit hook — source written at {touched} "
        f"(contents: {touched.read_text(encoding='utf-8')!r}); adopt must never invoke git "
        "commit or external hooks"
    )
    assert_source_tree_unchanged(
        root,
        before_hash=before_hash,
        before_bytes=before_bytes,
        legacy_code_globs=legacy,
    )

"""Shared helpers for Story 3.7 source-untouched property tests."""

from __future__ import annotations

import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

from sdlc.adopt.driver import run_adopt
from sdlc.adopt.passes import symlink_offer
from sdlc.adopt.rollback import rollback
from sdlc.adopt.tree_hash import compute_source_tree_hash, iter_source_relpaths
from sdlc.contracts.adopt_report import DetectedArtifact

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "brownfield"

CORPUS_FIXTURES = [
    "java-maven-service",
    "node-npm",
    "python-pyproject",
    "go-module",
    "monorepo-submodules",
    "preexisting-symlinks",
    "greenfield-disguised",
]


class AdoptInvocationMode(str, Enum):
    INTERACTIVE_ACCEPT_ALL = "interactive_accept_all"
    NON_INTERACTIVE_AUTO = "non_interactive_auto"
    PARTIAL_ACCEPT = "partial_accept"
    ROLLBACK_REDO = "rollback_redo"


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def init_git_repo(root: Path) -> None:
    if shutil.which("git") is None:
        import pytest

        pytest.skip("git not on PATH")
    git(["init"], root)
    git(["config", "user.email", "test@example.com"], root)
    git(["config", "user.name", "Test"], root)
    git(["config", "core.excludesFile", "/dev/null"], root)
    git(["add", "-A"], root)
    git(["commit", "-m", "initial"], root)


def copy_fixture(name: str, tmp_path: Path) -> Path:
    src = _FIXTURES_DIR / name
    dest = tmp_path / name
    # Hypothesis reuses a function-scoped tmp_path across examples (the function_scoped_fixture
    # healthcheck is suppressed), so a 2nd example would otherwise hit FileExistsError — start
    # each copy from a clean dest.
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def snapshot_source_bytes(root: Path, legacy_code_globs: tuple[str, ...] = ()) -> dict[str, bytes]:
    return {
        rel: (root / rel).read_bytes()
        for rel in iter_source_relpaths(root, legacy_code_globs=legacy_code_globs)
        if (root / rel).is_file() and not (root / rel).is_symlink()
    }


def porcelain_mutated_tracked(root: Path) -> list[str]:
    porcelain = git(["status", "--porcelain"], root).stdout
    return [
        line[3:]
        for line in porcelain.splitlines()
        if line.strip() and not line.startswith("??") and not line[3:].startswith(".claude/")
    ]


def assert_source_tree_unchanged(
    root: Path,
    *,
    before_hash: str,
    before_bytes: dict[str, bytes],
    legacy_code_globs: tuple[str, ...] = (),
) -> None:
    mutated = porcelain_mutated_tracked(root)
    assert mutated == [], f"adopt mutated tracked source files: {mutated}"
    after_hash = compute_source_tree_hash(root, legacy_code_globs=legacy_code_globs)
    assert after_hash == before_hash, "source tree hash changed"
    for rel, original in before_bytes.items():
        path = root / rel
        assert path.read_bytes() == original, f"source {rel} mutated"
        assert not path.is_symlink(), f"source {rel} was replaced by a symlink"


def _confirm_for_mode(mode: AdoptInvocationMode) -> symlink_offer.ConfirmCallback | None:
    if mode == AdoptInvocationMode.INTERACTIVE_ACCEPT_ALL:
        return lambda _artifact, target: symlink_offer.SymlinkDecision(accept=True, target=target)
    if mode == AdoptInvocationMode.PARTIAL_ACCEPT:
        calls = {"n": 0}

        def _partial(_artifact: DetectedArtifact, target: str) -> symlink_offer.SymlinkDecision:
            # Accept the first offer, skip the rest (partial-accept).
            calls["n"] += 1
            return symlink_offer.SymlinkDecision(accept=calls["n"] == 1, target=target)

        return _partial
    return None


def run_adopt_for_mode(root: Path, mode: AdoptInvocationMode) -> None:
    # Mirror the production journal location (cli/adopt.py: .claude/state/journal.log).
    journal_path = root / ".claude" / "state" / "journal.log"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    base_kwargs: dict[str, Any] = {
        "root": root,
        "journal_path": journal_path,
        "git_signal": {},
        "legacy_code_globs": (),
        "auto_accept_threshold": 80,
        "warn": None,
        "conflict": None,
    }
    if mode == AdoptInvocationMode.ROLLBACK_REDO:
        accept_all = _confirm_for_mode(AdoptInvocationMode.INTERACTIVE_ACCEPT_ALL)
        run_adopt(**base_kwargs, confirm=accept_all)
        rollback(root, targets=None, journal_path=journal_path)
        run_adopt(**base_kwargs, confirm=accept_all)
        return

    confirm = None if mode == AdoptInvocationMode.NON_INTERACTIVE_AUTO else _confirm_for_mode(mode)
    run_adopt(**base_kwargs, confirm=confirm)


def seed_preexisting_symlinks(root: Path) -> None:
    """POSIX-only: dangling README symlink + in-tree docs link (CR3.2-W1 corpus)."""
    (root / "README-link.md").symlink_to("missing-readme-target.md")
    (root / "docs" / "arch-link.md").symlink_to("architecture.md")
